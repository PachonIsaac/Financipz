from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db import models
from app.integrations import trm
from app.main import app
from app.services import integrations, refresh
from tests.api.binance_fake import API_KEY, API_SECRET
from tests.api.conftest import new_session
from tests.api.helpers import API, add_rate

D = Decimal
REFRESH = f"{API}/refresh"
TODAY = date(2026, 10, 27)


@pytest.fixture(autouse=True)
def forget_previous_run():
    refresh._last = None
    yield
    refresh._last = None


@pytest.fixture
def rates(monkeypatch):
    """The rate source: `calls` counts the history requests, `fail` makes every source unavailable."""
    state = {"calls": 0, "fail": False}

    def history(first, last):
        state["calls"] += 1
        if state["fail"]:
            raise trm.TrmError("down")
        return [trm.PublishedRate(TODAY, D("3158.43"))]

    def current():
        raise trm.TrmError("down")

    monkeypatch.setattr(trm, "fetch_history", history)
    monkeypatch.setattr(trm, "fetch_current", current)
    monkeypatch.setattr("app.services.fx_rates.local_today", lambda: TODAY)
    monkeypatch.setattr("app.services.refresh.local_today", lambda: TODAY)
    return state


@pytest.fixture
def connected(client, exchange):
    response = client.put(f"{API}/integrations/binance", json={"api_key": API_KEY, "api_secret": API_SECRET})
    assert response.status_code == 200, response.text
    return exchange


def test_it_requires_a_signed_in_user(client):
    app.dependency_overrides.pop(get_current_user)

    assert client.post(REFRESH).status_code == 401


def test_it_refreshes_both_sources(client, rates, connected, db):
    response = client.post(REFRESH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fx_rates"] == {"status": "ok", "code": None, "message": None}
    assert body["binance"] == {"status": "ok", "code": None, "message": None}
    assert body["cached"] is False and body["ran_at"]
    assert db.get(models.FxRate, (TODAY, "USD")).value == D("3158.4300")
    assert integrations.get_row(db, integrations.BINANCE).last_synced_at is not None


def test_an_exchange_that_is_not_connected_is_not_a_failure(client, rates, exchange):
    body = client.post(REFRESH).json()

    assert body["fx_rates"]["status"] == "ok"
    assert body["binance"]["status"] == "not_connected"
    assert body["binance"]["code"] == "integration_not_connected"
    assert exchange.requests == []


def test_a_forgotten_key_is_reported_as_not_connected(client, rates, connected):
    client.delete(f"{API}/integrations/binance")

    assert client.post(REFRESH).json()["binance"]["status"] == "not_connected"


def test_one_source_failing_does_not_stop_the_other(client, rates, connected, db):
    rates["fail"] = True

    response = client.post(REFRESH)

    assert response.status_code == 200
    body = response.json()
    assert body["fx_rates"]["status"] == "error"
    assert body["fx_rates"]["code"] == "fx_source_unavailable"
    assert body["fx_rates"]["message"]
    assert body["binance"]["status"] == "ok"
    assert integrations.get_row(db, integrations.BINANCE).last_synced_at is not None


def test_an_unexpected_failure_is_reported_without_its_text(client, rates, connected, monkeypatch):
    def boom(db, key):
        raise RuntimeError("https://example.invalid/?signature=SECRET")

    monkeypatch.setattr("app.services.binance_sync.sync_binance", boom)

    body = client.post(REFRESH).json()

    assert body["binance"] == {
        "status": "error",
        "code": "internal_error",
        "message": "Ocurrió un error inesperado. Intenta de nuevo.",
    }
    assert "SECRET" not in client.post(REFRESH).text


def test_a_second_press_inside_the_interval_reuses_the_result(client, rates, connected):
    first = client.post(REFRESH).json()
    second = client.post(REFRESH).json()

    assert (first["cached"], second["cached"]) == (False, True)
    assert second["ran_at"] == first["ran_at"]
    assert rates["calls"] == 1


def test_a_failed_run_is_tried_again_at_once(client, rates, connected):
    rates["fail"] = True
    client.post(REFRESH)
    rates["fail"] = False

    body = client.post(REFRESH).json()

    assert body["cached"] is False and body["fx_rates"]["status"] == "ok"
    assert rates["calls"] == 2


def test_it_runs_again_once_the_interval_has_passed(client, rates, connected):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, encryption_key=connected.encryption_key, refresh_min_interval_seconds=0
    )
    client.post(REFRESH)

    assert client.post(REFRESH).json()["cached"] is False
    assert rates["calls"] == 2


def test_it_is_stale_without_todays_rate(db, rates):
    assert refresh.is_stale(db)
    add_rate(db, date(2026, 10, 26), "3100")
    assert refresh.is_stale(db)
    add_rate(db, TODAY, "3158")
    assert not refresh.is_stale(db)


def test_a_connected_exchange_read_long_ago_is_stale(client, rates, connected, db):
    add_rate(db, TODAY, "3158")
    row = integrations.get_row(db, integrations.BINANCE)

    row.last_synced_at = None
    assert refresh.is_stale(db)
    row.last_synced_at = datetime.now(UTC) - timedelta(hours=7)
    assert refresh.is_stale(db)
    row.last_synced_at = datetime.now(UTC) - timedelta(hours=1)
    assert not refresh.is_stale(db)


def test_a_disconnected_exchange_never_makes_the_data_stale(client, rates, connected, db):
    add_rate(db, TODAY, "3158")
    client.delete(f"{API}/integrations/binance")

    assert not refresh.is_stale(db)


def test_the_startup_refresh_runs_when_stale_and_skips_when_fresh(client, rates, connected, connection):
    key = connected.encryption_key
    factory = lambda: new_session(connection)

    refresh.run_startup_refresh(factory, key)
    assert rates["calls"] == 1

    refresh._last = None
    refresh.run_startup_refresh(factory, key)
    assert rates["calls"] == 1  # fresh now


def test_the_startup_refresh_never_raises(rates):
    def broken():
        raise RuntimeError("connection refused")

    refresh.run_startup_refresh(broken, "unused")


def test_the_startup_refresh_leaves_a_run_in_progress_alone(client, rates, connected, connection):
    with refresh._lock:
        refresh.run_startup_refresh(lambda: new_session(connection), connected.encryption_key)

    assert rates["calls"] == 0


def test_the_service_starts_a_refresh_only_when_asked(monkeypatch):
    started = []
    monkeypatch.setattr(refresh, "start_in_background", lambda settings: started.append(settings))

    for enabled in (False, True):
        monkeypatch.setattr("app.main.settings", Settings(_env_file=None, database_url="postgresql+psycopg://x/y", refresh_on_startup=enabled))
        with TestClient(app):
            pass

    assert len(started) == 1
