from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select

from app.domain.entities import Currency
from app.domain.errors import DomainError
from app.db import models
from app.integrations import trm
from app.services import fx_rates
from tests.api.helpers import API, add_rate, error_code

D = Decimal
TODAY = date(2026, 10, 26)

CURRENT_BODY = '{"unidad": "COP", "nombre": "TRM", "valor": 3158.43, "fechaActualizacion": "2026-10-26T21:01:10.043Z"}'


def period(first: str, last: str, value: str = "3158.43", unit: str = "COP") -> dict:
    return {
        "valor": value,
        "unidad": unit,
        "vigenciadesde": f"{first}T00:00:00.000",
        "vigenciahasta": f"{last}T00:00:00.000",
    }


PORTAL_ROWS = [period("2026-10-23", "2026-10-23", "3185.01"), period("2026-10-24", "2026-10-26", "3158.43")]


@pytest.fixture
def remote(monkeypatch):
    """Replace the network. `portal` and `current` are handlers; `requests` records every call."""
    state = {
        "portal": lambda request: httpx.Response(200, json=PORTAL_ROWS),
        "current": lambda request: httpx.Response(200, text=CURRENT_BODY),
        "requests": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        kind = "portal" if request.url.host == "www.datos.gov.co" else "current"
        return state[kind](request)

    monkeypatch.setattr(
        trm, "build_client", lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    )
    monkeypatch.setattr("app.services.fx_rates.local_today", lambda: TODAY)
    return state


def down(request):
    return httpx.Response(500, text="boom")


def stored(db) -> dict:
    return {row.date: (row.value, row.source) for row in db.scalars(select(models.FxRate))}


def count_rows(db) -> int:
    return db.scalar(select(func.count()).select_from(models.FxRate))


def test_sync_stores_one_row_per_day_from_the_portal_periods(client, db, remote):
    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 200
    assert response.json() == {"date": "2026-10-26", "currency": "USD", "value": "3158.4300", "source": "trm_open_data"}
    assert stored(db) == {
        date(2026, 10, 23): (D("3185.01"), "trm_open_data"),
        date(2026, 10, 24): (D("3158.43"), "trm_open_data"),
        date(2026, 10, 25): (D("3158.43"), "trm_open_data"),
        date(2026, 10, 26): (D("3158.43"), "trm_open_data"),
    }
    # The first sync reads the last days only, and the fallback service is not needed.
    where = remote["requests"][0].url.params["$where"]
    assert "vigenciahasta >= '2026-10-19" in where and "vigenciadesde <= '2026-10-26" in where
    assert len(remote["requests"]) == 1


def test_a_period_is_cut_at_today(client, db, remote):
    remote["portal"] = lambda request: httpx.Response(200, json=[period("2026-10-25", "2026-10-28", "3100")])

    client.post(f"{API}/fx-rates/sync")

    assert sorted(stored(db)) == [date(2026, 10, 25), date(2026, 10, 26)]


def test_syncing_twice_updates_without_duplicating(client, db, remote):
    client.post(f"{API}/fx-rates/sync")
    remote["portal"] = lambda request: httpx.Response(200, json=[period("2026-10-24", "2026-10-26", "3170.10")])

    response = client.post(f"{API}/fx-rates/sync")

    assert response.json()["value"] == "3170.1000"
    assert count_rows(db) == 4


def test_sync_fills_the_gap_since_the_last_stored_day(client, db, remote):
    add_rate(db, date(2026, 10, 10), "3000")
    remote["portal"] = lambda request: httpx.Response(200, json=[period("2026-10-08", "2026-10-26", "3100")])

    client.post(f"{API}/fx-rates/sync")

    days = sorted(stored(db))
    # Re-reads a few days before the last stored one, then fills everything up to today.
    assert "vigenciahasta >= '2026-10-07" in remote["requests"][0].url.params["$where"]
    assert days[0] == date(2026, 10, 8) and days[-1] == TODAY and len(days) == 19
    assert stored(db)[date(2026, 10, 10)] == (D("3100"), "trm_open_data")


def test_the_catch_up_is_capped(client, db, remote):
    add_rate(db, date(2020, 1, 1), "3000")
    remote["portal"] = lambda request: httpx.Response(200, json=[])

    response = client.post(f"{API}/fx-rates/sync")

    cap = TODAY - timedelta(days=400)
    assert f"vigenciahasta >= '{cap.isoformat()}" in remote["requests"][0].url.params["$where"]
    # No newer rate exists, so the answer is the last one stored.
    assert response.json()["date"] == "2020-01-01"


def test_the_fallback_is_used_when_the_portal_is_down(client, db, remote):
    remote["portal"] = down

    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 200
    assert response.json() == {"date": "2026-10-26", "currency": "USD", "value": "3158.4300", "source": "trm_api"}
    assert count_rows(db) == 1


def test_the_fallback_never_replaces_an_official_row(client, db, remote):
    db.add(models.FxRate(date=TODAY, currency="USD", value=D("3200"), source="trm_open_data"))
    db.commit()
    remote["portal"] = down

    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 200
    assert response.json()["value"] == "3200.0000"
    assert stored(db)[TODAY] == (D("3200"), "trm_open_data")


def test_an_official_value_replaces_a_fallback_row(client, db, remote):
    db.add(models.FxRate(date=TODAY, currency="USD", value=D("3000"), source="trm_api"))
    db.commit()

    client.post(f"{API}/fx-rates/sync")

    assert stored(db)[TODAY] == (D("3158.43"), "trm_open_data")


def test_when_every_source_fails_it_is_a_502_and_nothing_is_written(client, db, remote):
    remote["portal"] = down
    remote["current"] = down

    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 502
    assert error_code(response) == "fx_source_unavailable"
    assert "TRM" in response.json()["error"]["message"]
    assert count_rows(db) == 0


def test_an_unreachable_source_is_a_502(client, db, remote):
    def unreachable(request):
        raise httpx.ConnectError("no route")

    remote["portal"] = unreachable
    remote["current"] = unreachable

    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 502
    assert count_rows(db) == 0


def test_a_failed_sync_keeps_what_was_stored(client, db, remote):
    client.post(f"{API}/fx-rates/sync")
    remote["portal"] = down
    remote["current"] = down

    assert client.post(f"{API}/fx-rates/sync").status_code == 502

    assert stored(db)[TODAY] == (D("3158.43"), "trm_open_data")


BAD_VALUES = ["1e40", "-5", "0", "999.99", "10000.01", "NaN", "Infinity", "-Infinity", '"abc"', "null", "1e-40"]


@pytest.mark.parametrize("value", BAD_VALUES)
def test_garbage_rates_from_both_sources_are_a_502_and_write_nothing(client, db, remote, value):
    quoted = value
    remote["portal"] = lambda request: httpx.Response(
        200, text='[{"valor": %s, "unidad": "COP", "vigenciadesde": "2026-10-26T00:00:00.000", '
                  '"vigenciahasta": "2026-10-26T00:00:00.000"}]' % quoted
    )
    remote["current"] = lambda request: httpx.Response(200, text=CURRENT_BODY.replace("3158.43", quoted))

    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 502, response.text
    assert error_code(response) == "fx_source_unavailable"
    assert count_rows(db) == 0


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]]",
        '{"unidad": "COP"}',
        '[{"valor": "3100"}]',
        '["x"]',
        '[{"valor": "3100", "unidad": "EUR", "vigenciadesde": "2026-10-26T00:00:00", "vigenciahasta": "2026-10-26T00:00:00"}]',
        '[{"valor": "3100", "unidad": "COP", "vigenciadesde": "2026-10-26T00:00:00", "vigenciahasta": "2026-10-20T00:00:00"}]',
        '[{"valor": "3100", "unidad": "COP", "vigenciadesde": "2020-10-26T00:00:00", "vigenciahasta": "2026-10-20T00:00:00"}]',
        '[{"valor": "3100", "unidad": "COP", "vigenciadesde": "soon", "vigenciahasta": "later"}]',
    ],
)
def test_odd_portal_answers_are_rejected(client, db, remote, text):
    remote["portal"] = lambda request: httpx.Response(200, text=text)
    remote["current"] = down

    assert client.post(f"{API}/fx-rates/sync").status_code == 502
    assert count_rows(db) == 0


@pytest.mark.parametrize(
    "body",
    [
        CURRENT_BODY.replace('"COP"', '"EUR"'),
        '{"unidad": "COP", "valor": 3158.43}',
        "[]",
        "not json",
    ],
)
def test_odd_fallback_answers_are_rejected(client, db, remote, body):
    remote["portal"] = down
    remote["current"] = lambda request: httpx.Response(200, text=body)

    assert client.post(f"{API}/fx-rates/sync").status_code == 502
    assert count_rows(db) == 0


def test_the_portal_pagination_is_bounded(client, db, remote, monkeypatch):
    monkeypatch.setattr(trm, "HISTORY_PAGE_SIZE", 1)
    monkeypatch.setattr(trm, "MAX_HISTORY_PAGES", 3)
    remote["portal"] = lambda request: httpx.Response(200, json=[period("2026-10-26", "2026-10-26")])
    remote["current"] = down

    response = client.post(f"{API}/fx-rates/sync")

    assert response.status_code == 502
    assert len([r for r in remote["requests"] if r.url.host == "www.datos.gov.co"]) == 3
    assert count_rows(db) == 0


def test_redirects_are_not_followed(client, db, remote):
    remote["portal"] = lambda request: httpx.Response(302, headers={"location": "http://elsewhere.invalid/"})
    remote["current"] = lambda request: httpx.Response(302, headers={"location": "http://elsewhere.invalid/"})

    assert client.post(f"{API}/fx-rates/sync").status_code == 502
    assert len(remote["requests"]) == 2


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


def test_a_date_returns_that_days_rate_or_the_closest_earlier(client, db):
    add_rate(db, date(2026, 10, 2), "3102")
    add_rate(db, date(2026, 10, 9), "3109")

    exact = client.get(f"{API}/fx-rates", params={"date": "2026-10-09"})
    earlier = client.get(f"{API}/fx-rates", params={"date": "2026-10-04"})

    assert exact.status_code == 200 and exact.json()["date"] == "2026-10-09"
    assert earlier.json() == {"date": "2026-10-02", "currency": "USD", "value": "3102.0000", "source": "test"}


def test_a_date_before_any_rate_is_a_404(client, db):
    add_rate(db, date(2026, 10, 2), "3102")

    response = client.get(f"{API}/fx-rates", params={"date": "2026-10-01"})

    assert response.status_code == 404
    assert error_code(response) == "not_found"


@pytest.mark.parametrize("extra", [{"from": "2026-10-01"}, {"to": "2026-10-30"}])
def test_date_and_range_are_mutually_exclusive(client, extra):
    response = client.get(f"{API}/fx-rates", params={"date": "2026-10-05", **extra})

    assert response.status_code == 422
    assert error_code(response) == "invalid_filters"


@pytest.mark.parametrize(
    "params", [{"from": "nope"}, {"to": "2026-13-01"}, {"date": "x"}, {"from": "2026-10-05", "to": "2026-10-01"}]
)
def test_list_rejects_bad_parameters(client, params):
    response = client.get(f"{API}/fx-rates", params=params)

    assert response.status_code == 422
    assert error_code(response) in {"validation_error", "invalid_range"}


def test_load_rates_reads_the_window_and_the_rate_before_it(db):
    for day, value in [(date(2026, 1, 1), "3001"), (date(2026, 2, 20), "3002"), (date(2026, 3, 5), "3003"),
                       (date(2026, 4, 1), "3004")]:
        add_rate(db, day, value)

    rates = fx_rates.load_rates(db, date(2026, 3, 1), date(2026, 4, 1))

    # The day before the window's first rate uses the closest earlier one; later rates are left out.
    assert rates.rate(Currency.USD, date(2026, 3, 1)) == D("3002")
    assert rates.rate(Currency.USD, date(2026, 3, 31)) == D("3003")
    with pytest.raises(DomainError):
        rates.rate(Currency.USD, date(2026, 2, 1))


def test_sync_with_an_explicit_start_backfills(db, remote):
    remote["portal"] = lambda request: httpx.Response(200, json=[period("2026-09-01", "2026-09-03", "3000")])

    row = fx_rates.sync_rates(db, date(2026, 9, 1))

    assert "vigenciahasta >= '2026-09-01" in remote["requests"][0].url.params["$where"]
    assert row.date == date(2026, 9, 3)
    assert count_rows(db) == 3


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

    remote["portal"] = down
    remote["current"] = down
    assert sync_trm.main([]) == 1
    assert "fx_source_unavailable" in capsys.readouterr().err
