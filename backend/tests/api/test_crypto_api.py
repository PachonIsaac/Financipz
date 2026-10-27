import base64
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db import models
from app.domain.entities import LOCAL_TIMEZONE
from tests.api.helpers import API, add_rate, error_code

D = Decimal


@pytest.fixture
def exchange_account(db) -> models.Account:
    account = models.Account(name="Binance", type="exchange", currency="USD")
    db.add(account)
    db.commit()
    return account


def snapshot(db, account, day: date, assets: dict[str, tuple[str, str | None]]) -> None:
    for asset, (quantity, value) in assets.items():
        db.add(
            models.CryptoBalance(
                account_id=account.id, asset=asset, date=day, quantity=D(quantity),
                value_usd=None if value is None else D(value),
            )
        )
    db.commit()


def add_trade(db, account, pair: str, number: int, when: datetime, side: str = "buy") -> None:
    db.add(
        models.CryptoTrade(
            account_id=account.id, pair=pair, side=side, quantity=D("1"), price=D("100"), fee=D("0.1"),
            fee_asset="BNB", executed_at=when, external_id=f"{pair}:{number}",
        )
    )
    db.commit()


def test_portfolio_without_any_sync_is_empty(client):
    response = client.get(f"{API}/crypto/portfolio")

    assert response.status_code == 200
    assert response.json() == {
        "snapshot_date": None, "total_usd": None, "total_cop": None, "unpriced_assets": 0, "rate": None, "assets": [],
    }


def test_portfolio_shows_the_latest_snapshot_in_dollars_and_pesos(client, db, exchange_account):
    snapshot(db, exchange_account, date(2026, 10, 20), {"BTC": ("9", "9")})
    snapshot(
        db, exchange_account, date(2026, 10, 25),
        {"BTC": ("0.5", "40000.00"), "USDT": ("100", "100.00"), "OBSCURE": ("7.5", None)},
    )
    add_rate(db, date(2026, 10, 24), "4000.5")

    body = client.get(f"{API}/crypto/portfolio").json()

    assert body["snapshot_date"] == "2026-10-25"
    assert body["total_usd"] == "40100.00"
    assert body["total_cop"] == "160420050.00"
    assert body["unpriced_assets"] == 1
    assert body["rate"] == {"currency": "USD", "value": "4000.5000", "date": "2026-10-24"}
    assert [asset["asset"] for asset in body["assets"]] == ["BTC", "USDT", "OBSCURE"]
    btc, usdt, obscure = body["assets"]
    assert (btc["value_usd"], btc["value_cop"]) == ("40000.00", "160020000.00")
    assert D(btc["quantity"]) == D("0.5")
    assert (usdt["value_usd"], usdt["value_cop"]) == ("100.00", "400050.00")
    assert (obscure["value_usd"], obscure["value_cop"]) == (None, None)


def test_portfolio_without_a_rate_has_no_pesos(client, db, exchange_account):
    snapshot(db, exchange_account, date(2026, 10, 25), {"USDT": ("100", "100.00")})

    body = client.get(f"{API}/crypto/portfolio").json()

    assert body["total_usd"] == "100.00"
    assert body["total_cop"] is None and body["rate"] is None
    assert body["assets"][0]["value_cop"] is None


def test_history_has_one_total_per_synced_day_and_skips_the_rest(client, db, exchange_account):
    snapshot(db, exchange_account, date(2026, 10, 20), {"BTC": ("1", "100.50"), "USDT": ("5", "5.00")})
    snapshot(db, exchange_account, date(2026, 10, 22), {"BTC": ("1", "120.00"), "OBSCURE": ("1", None)})
    snapshot(db, exchange_account, date(2026, 10, 27), {"BTC": ("1", "130.00")})

    everything = client.get(f"{API}/crypto/history").json()
    ranged = client.get(f"{API}/crypto/history", params={"from": "2026-10-21", "to": "2026-10-26"}).json()

    assert everything == [
        {"date": "2026-10-20", "total_usd": "105.50"},
        {"date": "2026-10-22", "total_usd": "120.00"},
        {"date": "2026-10-27", "total_usd": "130.00"},
    ]
    assert ranged == [{"date": "2026-10-22", "total_usd": "120.00"}]


def test_history_of_a_day_with_only_unpriced_assets_is_zero(client, db, exchange_account):
    snapshot(db, exchange_account, date(2026, 10, 22), {"OBSCURE": ("1", None)})

    assert client.get(f"{API}/crypto/history").json() == [{"date": "2026-10-22", "total_usd": "0.00"}]


def test_history_rejects_an_inverted_range(client):
    response = client.get(f"{API}/crypto/history", params={"from": "2026-10-27", "to": "2026-10-01"})

    assert response.status_code == 422
    assert error_code(response) == "invalid_range"


def test_history_with_no_data_is_an_empty_list(client):
    assert client.get(f"{API}/crypto/history").json() == []


def make_trades(db, account) -> None:
    base = datetime(2026, 10, 20, 12, 0, tzinfo=LOCAL_TIMEZONE)
    for number in range(1, 6):
        add_trade(db, account, "BTCUSDT", number, base + timedelta(days=number))
    add_trade(db, account, "ETHUSDT", 1, base + timedelta(days=2, hours=1), side="sell")


def test_trades_are_listed_newest_first_with_every_field(client, db, exchange_account):
    make_trades(db, exchange_account)

    body = client.get(f"{API}/crypto/trades").json()

    assert body["next_cursor"] is None
    assert [item["external_id"] for item in body["items"]] == [
        "BTCUSDT:5", "BTCUSDT:4", "BTCUSDT:3", "ETHUSDT:1", "BTCUSDT:2", "BTCUSDT:1",
    ]
    first = body["items"][0]
    assert set(first) == {
        "id", "account_id", "pair", "side", "quantity", "price", "fee", "fee_asset", "executed_at", "external_id",
    }
    assert first["pair"] == "BTCUSDT" and first["side"] == "buy" and first["fee_asset"] == "BNB"
    assert first["executed_at"].startswith("2026-10-25T")


def test_trades_filter_by_pair_ignoring_case(client, db, exchange_account):
    make_trades(db, exchange_account)

    body = client.get(f"{API}/crypto/trades", params={"pair": "ethusdt"}).json()

    assert [item["external_id"] for item in body["items"]] == ["ETHUSDT:1"]
    assert body["items"][0]["side"] == "sell"


def test_trades_filter_by_dates_in_colombian_time(client, db, exchange_account):
    # 23:30 in Bogota on the 21st is already the 22nd in UTC: it belongs to the 21st.
    add_trade(db, exchange_account, "BTCUSDT", 1, datetime(2026, 10, 21, 23, 30, tzinfo=LOCAL_TIMEZONE))
    add_trade(db, exchange_account, "BTCUSDT", 2, datetime(2026, 10, 22, 0, 30, tzinfo=LOCAL_TIMEZONE))
    add_trade(db, exchange_account, "BTCUSDT", 3, datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc))

    only_21 = client.get(f"{API}/crypto/trades", params={"from": "2026-10-21", "to": "2026-10-21"}).json()
    from_22 = client.get(f"{API}/crypto/trades", params={"from": "2026-10-22"}).json()
    until_21 = client.get(f"{API}/crypto/trades", params={"to": "2026-10-21"}).json()

    assert [item["external_id"] for item in only_21["items"]] == ["BTCUSDT:1"]
    assert [item["external_id"] for item in from_22["items"]] == ["BTCUSDT:3", "BTCUSDT:2"]
    assert [item["external_id"] for item in until_21["items"]] == ["BTCUSDT:1"]


def test_trades_are_paginated_by_cursor_without_gaps_or_repeats(client, db, exchange_account):
    make_trades(db, exchange_account)

    seen = []
    cursor = None
    pages = 0
    while True:
        params = {"limit": 4, **({"cursor": cursor} if cursor else {})}
        body = client.get(f"{API}/crypto/trades", params=params).json()
        seen += [item["external_id"] for item in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break

    assert pages == 2
    assert seen == ["BTCUSDT:5", "BTCUSDT:4", "BTCUSDT:3", "ETHUSDT:1", "BTCUSDT:2", "BTCUSDT:1"]


@pytest.mark.parametrize("params", [{"cursor": "garbage"}, {"cursor": "bm90LWEtY3Vyc29y"}, {"limit": 0}, {"limit": 500}, {"pair": "BTC/USDT"}, {"from": "yesterday"}])
def test_invalid_trade_filters_use_the_standard_error(client, params):
    response = client.get(f"{API}/crypto/trades", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"invalid_cursor", "validation_error"}


def test_trades_reject_an_inverted_range(client):
    response = client.get(f"{API}/crypto/trades", params={"from": "2026-10-27", "to": "2026-10-01"})

    assert error_code(response) == "invalid_range"


def test_a_cursor_with_a_naive_date_is_refused(client):
    cursor = base64.urlsafe_b64encode(f"2026-10-21T10:00:00|{uuid.uuid4()}".encode()).decode()

    response = client.get(f"{API}/crypto/trades", params={"cursor": cursor})

    assert error_code(response) == "invalid_cursor"


def test_portfolio_converts_with_the_rate_of_the_snapshot_day_not_a_later_one(client, db, exchange_account):
    snapshot(db, exchange_account, date(2026, 10, 22), {"USDT": ("10", "10.00")})
    add_rate(db, date(2026, 10, 21), "4000")
    add_rate(db, date(2026, 10, 25), "5000")

    body = client.get(f"{API}/crypto/portfolio").json()

    assert body["total_cop"] == "40000.00"
    assert body["rate"]["date"] == "2026-10-21"


def test_portfolio_without_a_rate_on_or_before_the_snapshot_has_no_pesos(client, db, exchange_account):
    snapshot(db, exchange_account, date(2026, 10, 22), {"USDT": ("10", "10.00")})
    add_rate(db, date(2026, 10, 25), "5000")

    body = client.get(f"{API}/crypto/portfolio").json()

    assert body["total_cop"] is None and body["rate"] is None
