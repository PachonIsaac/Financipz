from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select

from app.db import models
from app.integrations import trm
from tests.api.helpers import API, add_rate, error_code

D = Decimal

CURRENT_BODY = '{"unidad": "COP", "nombre": "TRM", "valor": 3158.43, "fechaActualizacion": "2026-10-26T21:01:10.043Z"}'


@pytest.fixture
def remote(monkeypatch):
    """Replace the network with a handler; returns the list of requests it received."""
    state = {"handler": lambda request: httpx.Response(200, text=CURRENT_BODY), "requests": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        return state["handler"](request)

    monkeypatch.setattr(trm, "build_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr("app.services.fx_rates.local_today", lambda: date(2026, 10, 26))
    return state


def count_rows(db) -> int:
    return db.scalar(select(func.count()).select_from(models.FxRate))


def test_sync_stores_the_current_rate(client, db, remote):
    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 200
    assert response.json() == {"date": "2026-10-26", "currency": "USD", "value": "3158.4300", "source": "trm_api"}
    assert count_rows(db) == 1
    assert str(remote["requests"][0].url) == "https://co.dolarapi.com/v1/trm"


def test_the_day_is_the_colombian_day_of_the_update(client, remote):
    # 02:00 UTC on the 27th is still the evening of the 26th in Colombia.
    remote["handler"] = lambda request: httpx.Response(
        200, text=CURRENT_BODY.replace("2026-10-26T21:01:10.043Z", "2026-10-27T02:00:00.000Z")
    )

    assert client.post(f"{API}/fx-rates/sync").json()["date"] == "2026-10-26"


def test_syncing_twice_the_same_day_updates_without_duplicating(client, db, remote):
    client.post(f"{API}/fx-rates/sync")
    remote["handler"] = lambda request: httpx.Response(200, text=CURRENT_BODY.replace("3158.43", "3170.1"))

    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 200
    assert response.json()["value"] == "3170.1000"
    assert count_rows(db) == 1


def test_sync_keeps_other_days(client, db, remote):
    add_rate(db, date(2026, 10, 25), "3100")

    client.post(f"{API}/fx-rates/sync")

    assert count_rows(db) == 2


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500, text="boom"),
        lambda request: httpx.Response(200, text="not json"),
        lambda request: httpx.Response(200, text='{"unidad": "COP"}'),
        lambda request: httpx.Response(200, text=CURRENT_BODY.replace("3158.43", "0")),
        lambda request: httpx.Response(200, text=CURRENT_BODY.replace("3158.43", '"abc"')),
        lambda request: httpx.Response(200, text=CURRENT_BODY.replace('"COP"', '"EUR"')),
        lambda request: httpx.Response(200, text="[]"),
    ],
    ids=["server-error", "not-json", "missing-fields", "zero", "not-a-number", "other-unit", "wrong-shape"],
)
def test_a_failing_or_odd_source_is_a_502_and_writes_nothing(client, db, remote, handler):
    remote["handler"] = handler

    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 502
    assert error_code(response) == "fx_source_unavailable"
    assert "TRM" in response.json()["error"]["message"]
    assert count_rows(db) == 0


def test_an_unreachable_source_is_a_502(client, db, remote):
    def down(request):
        raise httpx.ConnectError("no route")

    remote["handler"] = down

    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 502
    assert error_code(response) == "fx_source_unavailable"
    assert count_rows(db) == 0


def test_a_failed_sync_keeps_the_stored_rate(client, db, remote):
    client.post(f"{API}/fx-rates/sync")
    remote["handler"] = lambda request: httpx.Response(503)

    assert client.post(f"{API}/fx-rates/sync").status_code == 502

    assert db.get(models.FxRate, (date(2026, 10, 26), "USD")).value == D("3158.43")


def test_list_is_ordered_and_filtered_by_range(client, db):
    for day, value in [(date(2026, 10, 3), "3103"), (date(2026, 10, 1), "3101"), (date(2026, 10, 2), "3102")]:
        add_rate(db, day, value)

    everything = client.get(f"{API}/fx-rates").json()
    ranged = client.get(f"{API}/fx-rates", params={"from": "2026-10-02", "to": "2026-10-02"}).json()
    from_only = client.get(f"{API}/fx-rates", params={"from": "2026-10-02"}).json()

    assert [item["date"] for item in everything] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    assert [item["value"] for item in ranged] == ["3102.0000"]
    assert [item["date"] for item in from_only] == ["2026-10-02", "2026-10-03"]


def test_list_with_no_rates_is_empty(client):
    assert client.get(f"{API}/fx-rates").json() == []


@pytest.mark.parametrize("params", [{"from": "nope"}, {"to": "2026-13-01"}, {"from": "2026-10-05", "to": "2026-10-01"}])
def test_list_rejects_bad_parameters(client, params):
    response = client.get(f"{API}/fx-rates", params=params)

    assert response.status_code == 422
    assert error_code(response) in {"validation_error", "invalid_range"}


def test_history_is_stored_without_future_days(db, remote, monkeypatch):
    from app.services import fx_rates

    rows = [
        {"valor": "3100.50", "unidad": "COP", "vigenciadesde": "2026-10-23T00:00:00.000", "vigenciahasta": "2026-10-25T00:00:00.000"},
        {"valor": "3158.43", "unidad": "COP", "vigenciadesde": "2026-10-26T00:00:00.000", "vigenciahasta": "2026-10-26T00:00:00.000"},
        {"valor": "3157.94", "unidad": "COP", "vigenciadesde": "2026-10-27T00:00:00.000", "vigenciahasta": "2026-10-27T00:00:00.000"},
    ]
    remote["handler"] = lambda request: httpx.Response(200, json=rows)

    written = fx_rates.backfill(db, date(2026, 10, 1))

    assert written == 2
    stored = {row.date: (row.value, row.source) for row in db.scalars(select(models.FxRate))}
    assert stored == {
        date(2026, 10, 23): (D("3100.50"), "trm_open_data"),
        date(2026, 10, 26): (D("3158.43"), "trm_open_data"),
    }
    assert "vigenciadesde >= '2026-10-01T00:00:00.000'" in str(remote["requests"][0].url.params["$where"])


def test_history_failure_is_a_502(db, remote):
    from app.core.errors import ApiError
    from app.services import fx_rates

    remote["handler"] = lambda request: httpx.Response(500)

    with pytest.raises(ApiError) as caught:
        fx_rates.backfill(db, date(2026, 10, 1))

    assert caught.value.status_code == 502
    assert count_rows(db) == 0


def test_the_job_reports_success_and_failure(db, remote, monkeypatch, capsys):
    from app.jobs import sync_trm

    class FakeSession:
        def __init__(self, engine):
            pass

        def __enter__(self):
            return db

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(sync_trm, "Session", FakeSession)
    monkeypatch.setattr(sync_trm, "get_engine", lambda url: None)
    monkeypatch.setattr(sync_trm, "get_settings", lambda: type("S", (), {"database_url": "x"})())

    assert sync_trm.main([]) == 0
    assert "3158.4300" in capsys.readouterr().out

    remote["handler"] = lambda request: httpx.Response(500)
    assert sync_trm.main([]) == 1
    assert "fx_source_unavailable" in capsys.readouterr().err
