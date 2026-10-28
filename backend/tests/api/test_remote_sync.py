from datetime import date
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.integrations import trm
from app.main import app
from app.services import binance_sync, integrations, refresh, remote_sync
from tests.api.binance_fake import API_KEY, API_SECRET
from tests.api.conftest import new_session
from tests.api.helpers import API, add_rate, error_code

WORKER = "https://worker.test/api/v1"
REFRESH = f"{API}/refresh"
SYNC = f"{API}/integrations/binance/sync"
AUTH = {"Authorization": "Bearer user-token"}
TODAY = date(2026, 10, 27)

SYNC_BODY = {
    "snapshot_date": "2026-10-27",
    "assets": 2,
    "unpriced_assets": 0,
    "total_usd": "1781.98",
    "new_trades": 3,
    "trades_complete": True,
    "warnings": [],
    "last_synced_at": "2026-10-27T15:00:00Z",
}


@pytest.fixture(autouse=True)
def forget_previous_run():
    refresh._last = None
    yield
    refresh._last = None


@pytest.fixture
def worker(monkeypatch):
    """The other deployment: `answer` is what it replies, `requests` what it was asked."""
    state = {"answer": lambda request: httpx.Response(200, json=SYNC_BODY), "requests": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        return state["answer"](request)

    real = httpx.Client
    monkeypatch.setattr(
        remote_sync.httpx,
        "Client",
        lambda **kwargs: real(transport=httpx.MockTransport(handler), **{k: v for k, v in kwargs.items() if k != "transport"}),
    )
    return state


@pytest.fixture
def delegating(client, exchange, monkeypatch):
    """This deployment hands the exchange to another one. Reading it directly must never happen."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, encryption_key=exchange.encryption_key, binance_sync_url=WORKER
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("the exchange must not be read from here")

    monkeypatch.setattr(binance_sync, "sync_binance", forbidden)
    monkeypatch.setattr("app.services.fx_rates.local_today", lambda: TODAY)
    monkeypatch.setattr("app.services.refresh.local_today", lambda: TODAY)
    return exchange


def test_the_sync_is_asked_to_the_other_deployment_with_the_same_token(delegating, worker):
    response = TestClient(app).post(SYNC, headers=AUTH)

    assert response.status_code == 200, response.text
    assert response.json()["total_usd"] == "1781.98"
    [request] = worker["requests"]
    assert str(request.url) == f"{WORKER}/integrations/binance/sync"
    assert request.method == "POST"
    assert request.headers["authorization"] == AUTH["Authorization"]


def test_without_a_token_nothing_is_sent(delegating, worker):

    response = TestClient(app).post(SYNC)

    assert response.status_code == 401
    assert worker["requests"] == []


@pytest.mark.parametrize("status", [401, 403])
def test_a_refusal_of_the_session_by_the_other_deployment_does_not_sign_the_person_out(delegating, worker, status):

    worker["answer"] = lambda request: httpx.Response(
        status, json={"error": {"code": "invalid_token", "message": "Token inválido.", "details": {}}}
    )

    response = TestClient(app).post(SYNC, headers=AUTH)

    assert response.status_code == 502
    assert error_code(response) == "binance_worker_rejected"


def test_the_error_of_the_other_deployment_reaches_the_person(delegating, worker):

    worker["answer"] = lambda request: httpx.Response(
        502, json={"error": {"code": "binance_region_blocked", "message": "Bloqueado.", "details": {}}}
    )

    response = TestClient(app).post(SYNC, headers=AUTH)

    assert response.status_code == 502
    assert error_code(response) == "binance_region_blocked"


def test_an_unreachable_or_garbled_other_deployment_is_reported_as_unavailable(delegating, worker):

    def down(request):
        raise httpx.ConnectError("refused")

    for answer in (down, lambda request: httpx.Response(200, text="<html>"), lambda request: httpx.Response(500, text="boom")):
        worker["answer"] = answer
        response = TestClient(app).post(SYNC, headers=AUTH)
        assert response.status_code == 502
        assert error_code(response) == "binance_worker_unavailable"


def test_the_refresh_reads_the_rate_here_and_the_exchange_there(delegating, worker, monkeypatch):


    monkeypatch.setattr(trm, "fetch_history", lambda first, last: [trm.PublishedRate(TODAY, Decimal("3158.43"))])

    body = TestClient(app).post(REFRESH, headers=AUTH).json()

    assert body["fx_rates"]["status"] == "ok"
    assert body["binance"]["status"] == "ok"
    assert len(worker["requests"]) == 1


def test_a_worker_without_an_exchange_connected_is_not_a_failure(delegating, worker, monkeypatch):


    monkeypatch.setattr(trm, "fetch_history", lambda first, last: [trm.PublishedRate(TODAY, Decimal("3158.43"))])
    worker["answer"] = lambda request: httpx.Response(
        409, json={"error": {"code": "integration_not_connected", "message": "Sin conexión.", "details": {}}}
    )

    body = TestClient(app).post(REFRESH, headers=AUTH).json()

    assert body["binance"]["status"] == "not_connected"


def test_the_startup_refresh_only_reads_the_rate_when_the_exchange_is_read_elsewhere(client, exchange, connection, worker, monkeypatch):


    calls = []
    monkeypatch.setattr(trm, "fetch_history", lambda first, last: calls.append(1) or [trm.PublishedRate(TODAY, Decimal("3158.43"))])
    monkeypatch.setattr("app.services.fx_rates.local_today", lambda: TODAY)
    monkeypatch.setattr("app.services.refresh.local_today", lambda: TODAY)

    refresh.run_startup_refresh(lambda: new_session(connection), exchange.encryption_key, exchange_elsewhere=True)

    assert calls == [1]
    assert worker["requests"] == []
    assert refresh._last is None  # a button press right after must still read the exchange


def test_the_exchange_does_not_make_the_data_stale_when_it_is_read_elsewhere(client, exchange, db, monkeypatch):
    monkeypatch.setattr("app.services.refresh.local_today", lambda: TODAY)
    client.put(f"{API}/integrations/binance", json={"api_key": API_KEY, "api_secret": API_SECRET})
    add_rate(db, TODAY, "3158")
    integrations.get_row(db, integrations.BINANCE).last_synced_at = None

    assert refresh.is_stale(db)
    assert not refresh.is_stale(db, check_exchange=False)
