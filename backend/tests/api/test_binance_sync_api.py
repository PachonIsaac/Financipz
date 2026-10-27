from datetime import date
from decimal import Decimal

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.db import models
from app.integrations import binance
from app.jobs import sync_binance
from app.main import app
from app.services import binance_sync
from tests.api.binance_fake import API_KEY, API_SECRET, balance, error, safe_restrictions, trade_row
from tests.api.helpers import API, error_code

D = Decimal
SYNC = f"{API}/integrations/binance/sync"
TODAY = date(2026, 10, 27)


@pytest.fixture
def connected(client, exchange):
    response = client.put(f"{API}/integrations/binance", json={"api_key": API_KEY, "api_secret": API_SECRET})
    assert response.status_code == 200, response.text
    exchange.requests.clear()
    return exchange


def sync(client):
    return client.post(SYNC)


def balances(db, day: date | None = None) -> dict[str, tuple[Decimal, Decimal | None]]:
    query = select(models.CryptoBalance)
    if day:
        query = query.where(models.CryptoBalance.date == day)
    return {row.asset: (row.quantity, row.value_usd) for row in db.scalars(query)}


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def integration(db) -> models.Integration:
    db.expire_all()
    return db.scalars(select(models.Integration).where(models.Integration.provider == "binance")).one()


def test_sync_without_a_connection_is_a_conflict(client, exchange):
    response = sync(client)

    assert response.status_code == 409
    assert error_code(response) == "integration_not_connected"


def test_sync_after_disconnecting_is_a_conflict(client, connected):
    client.delete(f"{API}/integrations/binance")

    response = sync(client)

    assert error_code(response) == "integration_not_connected"


def test_first_sync_creates_the_account_snapshot_and_trades(client, connected, db):
    connected.funding = [{"asset": "ETH", "free": "2", "locked": "0", "freeze": "0"}]
    connected.earn_flexible = [{"asset": "USDT", "totalAmount": "50"}]
    connected.earn_locked = [{"asset": "BTC", "amount": "0.25"}]
    connected.trades = {"BTCUSDT": [trade_row("BTCUSDT", 1, True, "70000", "0.1"), trade_row("BTCUSDT", 2, False, "75000", "0.05")]}

    response = sync(client)

    assert response.status_code == 200, response.text
    body = response.json()
    # BTC 0.5 + 0.25 spot + 0.25 earn = 1.0 at 80000; ETH 2 at 2500; USDT 100 + 50.
    assert body["snapshot_date"] == "2026-10-27"
    assert body["assets"] == 3
    assert body["unpriced_assets"] == 0
    assert body["total_usd"] == "85150.00"
    assert body["new_trades"] == 2
    assert body["trades_complete"] is True
    assert [warning["code"] for warning in body["warnings"]] == []
    assert body["last_synced_at"]

    assert balances(db) == {
        "BTC": (D("1"), D("80000")),
        "ETH": (D("2"), D("5000")),
        "USDT": (D("150"), D("150")),
    }
    account = db.scalars(select(models.Account)).one()
    assert (account.name, account.type, account.currency) == ("Binance", "exchange", "USD")
    trades = {t.external_id: t for t in db.scalars(select(models.CryptoTrade))}
    assert set(trades) == {"BTCUSDT:1", "BTCUSDT:2"}
    first = trades["BTCUSDT:1"]
    assert (first.pair, first.side, first.quantity, first.price, first.fee, first.fee_asset) == (
        "BTCUSDT", "buy", D("0.1"), D("70000"), D("0.001"), "BNB",
    )
    assert trades["BTCUSDT:2"].side == "sell"
    row = integration(db)
    assert row.status == "active" and row.last_synced_at is not None


def test_the_secret_is_only_sent_as_a_signature_never_in_a_url(client, connected):
    sync(client)

    for request in connected.requests:
        assert API_SECRET not in str(request.url)
    assert all(request.method == "GET" or request.url.path == "/sapi/v1/asset/get-funding-asset" for request in connected.requests)


def test_syncing_twice_the_same_day_updates_and_never_duplicates(client, connected, db):
    connected.trades = {"BTCUSDT": [trade_row("BTCUSDT", 1), trade_row("BTCUSDT", 2)]}
    first = sync(client).json()

    connected.spot = [balance("BTC", "2"), balance("USDT", "100")]
    second = sync(client)

    assert second.status_code == 200
    assert first["new_trades"] == 2 and second.json()["new_trades"] == 0
    assert count(db, models.CryptoBalance) == 2
    assert count(db, models.CryptoTrade) == 2
    assert count(db, models.Account) == 1
    assert balances(db, TODAY)["BTC"] == (D("2"), D("160000"))


def test_an_asset_that_disappears_during_the_day_leaves_todays_snapshot(client, connected, db):
    sync(client)
    connected.spot = [balance("USDT", "100")]

    sync(client)

    assert set(balances(db)) == {"USDT"}


def test_a_new_day_adds_rows_and_a_day_without_sync_has_none(client, connected, db, monkeypatch):
    sync(client)
    monkeypatch.setattr("app.services.binance_sync.local_today", lambda: date(2026, 10, 29))
    connected.spot = [balance("BTC", "1")]

    sync(client)

    rows = db.execute(select(models.CryptoBalance.date, models.CryptoBalance.asset)).all()
    assert sorted(rows) == [(TODAY, "BTC"), (TODAY, "USDT"), (date(2026, 10, 29), "BTC")]
    assert not any(day == date(2026, 10, 28) for day, _ in rows)


def test_zero_balances_are_not_stored(client, connected, db):
    connected.spot = [balance("BTC", "0"), balance("USDT", "5"), balance("ETH", "0", "0")]

    sync(client)

    assert set(balances(db)) == {"USDT"}


def test_assets_without_a_price_are_kept_with_a_null_value_and_counted(client, connected, db):
    connected.spot = [balance("USDT", "10"), balance("OBSCURE", "7.5")]

    body = sync(client).json()

    assert body["assets"] == 2 and body["unpriced_assets"] == 1
    assert body["total_usd"] == "10.00"
    assert balances(db)["OBSCURE"] == (D("7.5"), None)


def test_assets_are_valued_through_bitcoin_when_there_is_no_usdt_pair(client, connected, db):
    connected.spot = [balance("XYZ", "1000")]

    sync(client)

    assert balances(db)["XYZ"] == (D("1000"), D("800"))


def test_stablecoins_are_valued_at_one(client, connected, db):
    connected.spot = [balance("USDC", "12.345"), balance("FDUSD", "1")]

    sync(client)

    assert balances(db) == {"USDC": (D("12.345"), D("12.35")), "FDUSD": (D("1"), D("1"))}


def test_wallets_the_key_cannot_read_are_skipped_with_warnings(client, connected, db):
    connected.overrides["/sapi/v1/asset/get-funding-asset"] = error(401, -2015)
    connected.overrides["/sapi/v1/simple-earn/flexible/position"] = error(400, -2015)
    connected.earn_locked = [{"asset": "BNB", "amount": "1"}]

    response = sync(client)

    assert response.status_code == 200
    body = response.json()
    assert sorted(warning["code"] for warning in body["warnings"]) == ["earn_flexible_skipped", "funding_wallet_skipped"]
    assert "BNB" in balances(db)
    row = integration(db)
    assert row.status == "active"
    assert {warning["code"] for warning in row.warnings} == {"earn_flexible_skipped", "funding_wallet_skipped"}
    listed = client.get(f"{API}/integrations").json()[1]
    assert {warning["code"] for warning in listed["warnings"]} == {"earn_flexible_skipped", "funding_wallet_skipped"}


def test_a_key_not_restricted_by_ip_adds_its_warning_to_every_sync(client, connected):
    connected.restrictions = safe_restrictions(ipRestrict=False)

    body = sync(client).json()

    assert [warning["code"] for warning in body["warnings"]] == ["ip_not_restricted"]


def test_a_wallet_failure_that_is_not_about_permissions_aborts_and_writes_nothing(client, connected, db):
    connected.overrides["/sapi/v1/asset/get-funding-asset"] = error(503, -1000)

    response = sync(client)

    assert response.status_code == 502
    assert error_code(response) == "binance_unavailable"
    assert count(db, models.CryptoBalance) == 0
    assert count(db, models.Account) == 0
    assert integration(db).last_synced_at is None


@pytest.mark.parametrize(
    "flag", ["enableWithdrawals", "enableInternalTransfer", "permitsUniversalTransfer", "enableMargin",
             "enableFutures", "enableSpotAndMarginTrading", "enableVanillaOptions", "enablePortfolioMarginTrading"],
)
def test_a_key_that_gained_dangerous_permissions_is_refused_and_marked_as_error(client, connected, db, flag):
    connected.restrictions = safe_restrictions(**{flag: True})

    response = sync(client)

    assert response.status_code == 422
    assert error_code(response) == "binance_key_not_read_only"
    row = integration(db)
    assert row.status == "error"
    assert [warning["code"] for warning in row.warnings] == ["key_not_read_only"]
    assert connected.paths() == ["/sapi/v1/account/apiRestrictions"]
    assert count(db, models.CryptoBalance) == 0
    assert client.get(f"{API}/integrations").json()[1]["status"] == "error"


def test_reconnecting_a_safe_key_recovers_from_the_error_status(client, connected, db):
    connected.restrictions = safe_restrictions(enableWithdrawals=True)
    sync(client)
    connected.restrictions = safe_restrictions()

    assert sync(client).status_code == 200
    assert integration(db).status == "active"


def test_a_key_rejected_by_the_exchange_marks_the_integration_as_error(client, connected, db):
    connected.overrides["/api/v3/account"] = error(401, -2015)

    response = sync(client)

    assert response.status_code == 422
    assert error_code(response) == "binance_access_denied"
    assert integration(db).status == "error"
    assert count(db, models.CryptoBalance) == 0


def test_the_exchange_being_down_keeps_previous_data_and_the_status(client, connected, db):
    sync(client)
    before = balances(db)
    connected.overrides["/api/v3/account"] = error(503, -1000)

    response = sync(client)

    assert response.status_code == 502
    assert error_code(response) == "binance_unavailable"
    assert balances(db) == before
    assert integration(db).status == "active"


def test_a_rate_limit_before_any_data_is_read_aborts_cleanly(client, connected, db):
    connected.overrides["/api/v3/account"] = lambda request: httpx.Response(429, json={"code": -1003}, headers={"Retry-After": "12"})

    response = sync(client)

    assert response.status_code == 503
    assert error_code(response) == "binance_rate_limited"
    assert response.headers["Retry-After"] == "12"
    assert count(db, models.CryptoBalance) == 0


@pytest.mark.parametrize(
    "answer",
    [
        lambda request: httpx.Response(200, text="not json"),
        lambda request: httpx.Response(200, json={"balances": [{"asset": "BTC", "free": "oops", "locked": "0"}]}),
        lambda request: httpx.Response(200, json={"balances": "nope"}),
    ],
)
def test_garbled_balances_abort_without_writing(client, connected, db, answer):
    connected.overrides["/api/v3/account"] = answer

    response = sync(client)

    assert response.status_code == 502
    assert error_code(response) == "binance_bad_response"
    assert count(db, models.CryptoBalance) == 0
    assert count(db, models.Account) == 0


def test_garbled_prices_abort_without_writing(client, connected, db):
    connected.overrides["/api/v3/ticker/price"] = lambda request: httpx.Response(200, json={"not": "a list"})

    response = sync(client)

    assert response.status_code == 502
    assert count(db, models.CryptoBalance) == 0


def test_a_garbled_trade_aborts_the_whole_sync_so_nothing_is_half_written(client, connected, db):
    bad = trade_row("BTCUSDT", 2)
    bad["price"] = "0"
    connected.trades = {"BTCUSDT": [trade_row("BTCUSDT", 1), bad]}

    response = sync(client)

    assert response.status_code == 502
    assert error_code(response) == "binance_bad_response"
    assert count(db, models.CryptoBalance) == 0
    assert count(db, models.CryptoTrade) == 0
    assert integration(db).last_synced_at is None


def test_trades_that_go_backwards_are_a_bad_response(client, connected, db):
    connected.overrides["/api/v3/myTrades"] = lambda request: httpx.Response(
        200, json=[trade_row("BTCUSDT", 5), trade_row("BTCUSDT", 3)]
    )

    response = sync(client)

    assert response.status_code == 502
    assert count(db, models.CryptoTrade) == 0


def test_a_rate_limit_while_reading_trades_stops_cleanly_and_keeps_what_was_read(client, connected, db):
    connected.spot = [balance("BTC", "1"), balance("ETH", "1")]
    connected.trades = {"BTCUSDT": [trade_row("BTCUSDT", 1)], "ETHUSDT": [trade_row("ETHUSDT", 1)]}
    connected.overrides["/api/v3/myTrades"] = lambda request: (
        httpx.Response(429, json={"code": -1003}) if request.url.params["symbol"] == "ETHUSDT"
        else httpx.Response(200, json=connected.trades["BTCUSDT"])
    )

    response = sync(client)

    assert response.status_code == 200
    body = response.json()
    assert body["trades_complete"] is False
    assert "trades_incomplete" in [warning["code"] for warning in body["warnings"]]
    assert body["new_trades"] == 1
    assert set(balances(db)) == {"BTC", "ETH"}
    assert [t.external_id for t in db.scalars(select(models.CryptoTrade))] == ["BTCUSDT:1"]

    # The next sync, with the limit gone, picks up the rest.
    del connected.overrides["/api/v3/myTrades"]
    again = sync(client).json()
    assert again["new_trades"] == 1 and again["trades_complete"] is True
    assert count(db, models.CryptoTrade) == 2


def test_the_number_of_requests_per_sync_is_capped(client, connected, db, monkeypatch):
    monkeypatch.setattr(binance_sync, "MAX_REQUESTS_PER_SYNC", 8)
    connected.spot = [balance("BTC", "1"), balance("ETH", "1")]
    connected.prices.extend({"symbol": f"{asset}USDT", "price": "1"} for asset in ("BTC", "ETH"))

    body = sync(client).json()

    assert body["trades_complete"] is False
    assert len(connected.requests) <= 8
    assert count(db, models.CryptoBalance) == 2


def test_only_trades_after_the_last_stored_one_are_requested(client, connected, db):
    connected.trades = {"BTCUSDT": [trade_row("BTCUSDT", 1), trade_row("BTCUSDT", 2), trade_row("BTCUSDT", 3)]}
    sync(client)
    connected.requests.clear()
    connected.trades["BTCUSDT"] += [trade_row("BTCUSDT", 4), trade_row("BTCUSDT", 5)]

    body = sync(client).json()

    assert body["new_trades"] == 2
    assert connected.trade_requests()[0]["fromId"] == "4"
    assert count(db, models.CryptoTrade) == 5


def test_the_first_read_of_a_pair_starts_from_the_beginning(client, connected):
    sync(client)

    assert {params["fromId"] for params in connected.trade_requests()} == {"0"}


def test_trades_are_read_page_by_page(client, connected, db, monkeypatch):
    monkeypatch.setattr(binance, "TRADES_PAGE_SIZE", 2)
    connected.trades = {"BTCUSDT": [trade_row("BTCUSDT", number) for number in range(1, 6)]}

    body = sync(client).json()

    assert body["new_trades"] == 5
    assert [params["fromId"] for params in connected.trade_requests() if params["symbol"] == "BTCUSDT"] == ["0", "3", "5"]


def test_pagination_has_a_bound_and_reports_it(client, connected, db, monkeypatch):
    monkeypatch.setattr(binance, "TRADES_PAGE_SIZE", 1)
    monkeypatch.setattr(binance_sync, "MAX_PAGES_PER_SYMBOL", 2)
    connected.trades = {"BTCUSDT": [trade_row("BTCUSDT", number) for number in range(1, 10)]}

    body = sync(client).json()

    assert body["trades_complete"] is False
    assert body["new_trades"] == 2


def test_the_same_trade_id_in_two_pairs_is_two_trades(client, connected, db):
    connected.spot = [balance("BTC", "1"), balance("ETH", "1")]
    connected.trades = {"BTCUSDT": [trade_row("BTCUSDT", 7)], "ETHUSDT": [trade_row("ETHUSDT", 7)]}

    body = sync(client).json()

    assert body["new_trades"] == 2
    assert {t.external_id for t in db.scalars(select(models.CryptoTrade))} == {"BTCUSDT:7", "ETHUSDT:7"}


def test_only_pairs_of_held_assets_or_traded_before_and_listed_are_read(client, connected, db):
    connected.spot = [balance("ETH", "1")]
    sync(client)
    requested = {params["symbol"] for params in connected.trade_requests()}
    # ETH against the quotes the exchange lists; nothing for assets that are not held.
    assert requested == {"ETHUSDT", "ETHBTC"}

    # A pair traded before keeps being read even if its asset was sold out.
    connected.trades = {"XYZBTC": [trade_row("XYZBTC", 1)]}
    connected.spot = [balance("XYZ", "1")]
    sync(client)
    connected.spot = [balance("ETH", "1")]
    connected.requests.clear()
    sync(client)
    assert "XYZBTC" in {params["symbol"] for params in connected.trade_requests()}


def test_an_unknown_pair_is_skipped_without_failing_the_sync(client, connected, db):
    connected.overrides["/api/v3/myTrades"] = error(400, -1121, "Invalid symbol.")

    response = sync(client)

    assert response.status_code == 200
    assert response.json()["trades_complete"] is True


def test_an_existing_exchange_account_in_dollars_is_reused(client, connected, db):
    db.add(models.Account(name="My exchange", type="exchange", currency="USD"))
    db.commit()

    sync(client)

    assert [a.name for a in db.scalars(select(models.Account))] == ["My exchange"]
    assert {row.account_id for row in db.scalars(select(models.CryptoBalance))} == {db.scalars(select(models.Account)).one().id}


def test_an_archived_exchange_account_is_not_reused(client, connected, db):
    db.add(models.Account(name="Old", type="exchange", currency="USD", archived=True))
    db.commit()

    sync(client)

    accounts = {a.name: a for a in db.scalars(select(models.Account))}
    assert set(accounts) == {"Old", "Binance"}


def test_the_account_stays_out_of_the_cash_flow_and_savings_numbers(client, connected):
    client.post(f"{API}/accounts", json={"name": "Bank", "type": "bank", "currency": "COP", "initial_balance": "100000"})
    before = client.get(f"{API}/wealth").json()

    sync(client)
    after = client.get(f"{API}/wealth").json()

    for field in ("available", "real_money", "credit_card_debt", "receivable_loans"):
        assert after[field] == before[field]
    assert after["available"] == "100000.00"


def test_a_missing_encryption_key_makes_sync_fail_closed(client, connected):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, encryption_key="")

    response = sync(client)

    assert response.status_code == 503
    assert error_code(response) == "encryption_not_configured"
    assert connected.requests == []


def test_a_different_encryption_key_cannot_read_the_stored_credentials(client, connected):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, encryption_key=Fernet.generate_key().decode())

    response = sync(client)

    assert response.status_code == 503
    assert error_code(response) == "credentials_unreadable"
    assert connected.requests == []


def run_job_on(db, exchange, monkeypatch) -> None:
    """Point the job at the test session and the fake exchange."""

    class FakeSettings:
        database_url = "postgresql+psycopg://invented"
        encryption_key = exchange.encryption_key

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return db

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(sync_binance, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(sync_binance, "get_engine", lambda url: None)
    monkeypatch.setattr(sync_binance, "Session", FakeSession)


def test_the_job_entry_point_syncs(client, connected, db, monkeypatch, capsys):
    run_job_on(db, connected, monkeypatch)

    assert sync_binance.main() == 0
    assert "Snapshot 2026-10-27" in capsys.readouterr().out
    assert count(db, models.CryptoBalance) == 2


def test_the_job_reports_failures_without_a_traceback(client, connected, db, monkeypatch, capsys):
    connected.restrictions = safe_restrictions(enableWithdrawals=True)
    run_job_on(db, connected, monkeypatch)

    assert sync_binance.main() == 1
    assert "binance_key_not_read_only" in capsys.readouterr().err
