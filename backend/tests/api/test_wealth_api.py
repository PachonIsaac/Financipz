from datetime import date
from decimal import Decimal

from app.db import models
from tests.api.helpers import API, add_rate, create_account, create_transaction, error_code

D = Decimal


def wealth(client):
    response = client.get(f"{API}/wealth")
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_database(client):
    body = wealth(client)

    assert body["available"] == "0.00"
    assert body["credit_card_debt"] == "0.00"
    assert body["real_money"] == "0.00"
    assert body["receivable_loans"] == "0.00"
    assert body["loans"] == []
    assert body["accounts"] == []
    assert body["crypto"] == {"value_usd": None, "value_cop": None, "snapshot_date": None, "unpriced_assets": 0}
    assert body["rate"] is None


def test_real_money_is_available_minus_card_debt(client):
    create_account(client, name="Cash", type="cash", initial=100_000)
    create_account(client, name="Bank", type="bank", initial=400_000)
    create_account(client, name="Savings", type="savings", initial=300_000)
    create_account(client, name="Wallet", type="wallet", initial=200_000)
    card = create_account(client, name="Card", type="credit_card")
    create_transaction(client, card, "expense", 300_000)

    body = wealth(client)

    assert body["available"] == "1000000.00"
    assert body["credit_card_debt"] == "300000.00"
    assert body["real_money"] == "700000.00"


def test_real_money_can_be_negative(client):
    create_account(client, name="Bank", type="bank", initial=200_000)
    card = create_account(client, name="Card", type="credit_card")
    create_transaction(client, card, "expense", 500_000)

    body = wealth(client)

    assert body["real_money"] == "-300000.00"
    card_row = next(item for item in body["accounts"] if item["name"] == "Card")
    assert card_row["balance"] == "-500000.00"


def test_negative_bank_balance_lowers_available(client):
    bank = create_account(client, name="Bank", type="bank", initial=50_000)
    create_transaction(client, bank, "expense", 80_000)

    body = wealth(client)

    assert body["available"] == "-30000.00"
    assert body["real_money"] == "-30000.00"


def test_loans_are_apart_from_real_money_and_listed_per_person(client):
    bank = create_account(client, name="Bank", type="bank", initial=1_000_000)
    ana = create_account(client, name="Loan Ana", type="loan", counterparty="Ana")
    luis = create_account(client, name="Loan Luis", type="loan", counterparty="Luis")
    create_transaction(client, bank, "transfer", 200_000, target_account_id=ana["id"], classification="loan")
    create_transaction(client, bank, "transfer", 50_000, target_account_id=luis["id"], classification="loan")

    body = wealth(client)

    assert body["available"] == "750000.00"
    assert body["real_money"] == "750000.00"
    assert body["receivable_loans"] == "250000.00"
    assert {(item["account_id"], item["counterparty"], item["amount"]) for item in body["loans"]} == {
        (ana["id"], "Ana", "200000.00"),
        (luis["id"], "Luis", "50000.00"),
    }


def test_exchange_and_system_accounts_stay_out_of_available(client, db):
    create_account(client, name="Bank", type="bank", initial=100_000)
    create_account(client, name="Exchange", type="exchange", initial=999_000)
    db.add(models.Account(name="Unknown origin", type="system", currency="COP", initial_balance=D("5000")))
    db.commit()

    body = wealth(client)

    assert body["available"] == "100000.00"
    assert {item["type"] for item in body["accounts"]} == {"bank", "exchange", "system"}


def test_archived_account_with_money_still_counts(client):
    keep = create_account(client, name="Old savings", type="savings", initial=250_000)
    empty = create_account(client, name="Old empty", type="bank")
    for account in (keep, empty):
        assert client.patch(f"{API}/accounts/{account['id']}", json={"archived": True}).status_code == 200

    body = wealth(client)

    assert body["available"] == "250000.00"
    assert [item["name"] for item in body["accounts"]] == ["Old savings"]
    assert body["accounts"][0]["archived"] is True


def test_usd_balances_are_valued_with_the_latest_rate(client, db):
    add_rate(db, date(2026, 1, 5), "3900")
    add_rate(db, date(2026, 10, 20), "4000.5")
    add_rate(db, date(2099, 1, 1), "9999")
    create_account(client, name="Bank", type="bank", initial=100_000)
    usd = create_account(client, name="Dollars", type="savings", currency="USD", initial=100)
    card = create_account(client, name="Card USD", type="credit_card", currency="USD")
    create_transaction(client, card, "expense", 10, date="2026-10-21T10:00:00-05:00")

    body = wealth(client)

    assert body["rate"] == {"currency": "USD", "value": "4000.5000", "date": "2026-10-20"}
    assert body["available"] == "500050.00"
    assert body["credit_card_debt"] == "40005.00"
    assert body["real_money"] == "460045.00"
    by_name = {item["name"]: item for item in body["accounts"]}
    assert by_name["Dollars"]["currency"] == "USD"
    assert by_name["Dollars"]["balance"] == "100.00"
    assert by_name["Dollars"]["balance_cop"] == "400050.00"
    assert by_name["Card USD"]["balance"] == "-10.00"
    assert by_name["Card USD"]["balance_cop"] == "-40005.00"
    assert usd["id"] == by_name["Dollars"]["id"]


def test_usd_balance_without_a_rate_is_a_clear_error(client):
    create_account(client, name="Dollars", type="savings", currency="USD", initial=100)

    response = client.get(f"{API}/wealth")

    assert response.status_code == 409
    assert error_code(response) == "missing_fx_rate"


def test_empty_usd_account_without_a_rate_is_worth_zero(client):
    create_account(client, name="Bank", type="bank", initial=10_000)
    create_account(client, name="Dollars", type="savings", currency="USD")

    body = wealth(client)

    assert body["available"] == "10000.00"
    assert body["rate"] is None
    dollars = next(item for item in body["accounts"] if item["name"] == "Dollars")
    assert dollars["balance_cop"] == "0.00"


def test_a_usd_exchange_account_needs_no_rate(client):
    create_account(client, name="Bank", type="bank", initial=10_000)
    exchange = create_account(client, name="Exchange USD", type="exchange", currency="USD", initial=50)

    response = client.get(f"{API}/wealth")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] == "10000.00"
    row = next(item for item in body["accounts"] if item["id"] == exchange["id"])
    assert row["balance"] == "50.00"
    assert row["balance_cop"] is None


def add_snapshot(db, account_id, day: date, assets: dict[str, tuple[str, str | None]]) -> None:
    for asset, (quantity, value) in assets.items():
        db.add(
            models.CryptoBalance(
                account_id=account_id, asset=asset, date=day, quantity=D(quantity),
                value_usd=None if value is None else D(value),
            )
        )
    db.commit()


def test_crypto_block_comes_from_the_latest_snapshot_in_dollars_and_pesos(client, db):
    add_rate(db, date(2026, 10, 20), "4000.5")
    exchange = create_account(client, name="Binance", type="exchange", currency="USD")
    add_snapshot(db, exchange["id"], date(2026, 10, 1), {"BTC": ("1", "999")})
    add_snapshot(db, exchange["id"], date(2026, 10, 26), {"BTC": ("0.5", "40000.00"), "USDT": ("10", "10.00"), "OBSCURE": ("1", None)})

    body = wealth(client)

    assert body["crypto"] == {
        "value_usd": "40010.00", "value_cop": "160060005.00", "snapshot_date": "2026-10-26", "unpriced_assets": 1,
    }


def test_crypto_block_without_a_rate_has_dollars_only(client, db):
    exchange = create_account(client, name="Binance", type="exchange", currency="USD")
    add_snapshot(db, exchange["id"], date(2026, 10, 26), {"USDT": ("10", "10.00")})

    body = wealth(client)

    assert body["crypto"] == {"value_usd": "10.00", "value_cop": None, "snapshot_date": "2026-10-26", "unpriced_assets": 0}


def test_crypto_never_changes_the_savings_numbers(client, db):
    add_rate(db, date(2026, 10, 20), "4000")
    create_account(client, name="Bank", type="bank", initial=100_000)
    exchange = create_account(client, name="Binance", type="exchange", currency="USD")
    before = wealth(client)

    add_snapshot(db, exchange["id"], date(2026, 10, 26), {"BTC": ("1", "80000.00")})
    after = wealth(client)

    for field in ("available", "credit_card_debt", "real_money", "receivable_loans", "loans", "accounts"):
        assert after[field] == before[field]
    assert after["crypto"]["value_usd"] == "80000.00"


def test_crypto_block_uses_the_rate_of_the_snapshot_day_not_todays(client, db):
    add_rate(db, date(2026, 10, 20), "4000")
    add_rate(db, date(2026, 10, 26), "5000")
    exchange = create_account(client, name="Binance", type="exchange", currency="USD")
    add_snapshot(db, exchange["id"], date(2026, 10, 22), {"USDT": ("10", "10.00")})

    body = wealth(client)

    assert body["crypto"]["value_cop"] == "40000.00"


def test_accounts_left_out_of_the_balance_do_not_count(client):
    create_account(client, name="Bank", type="bank", initial=400_000)
    left_out = create_account(client, name="Savings", type="savings", initial=300_000)
    card = create_account(client, name="Card", type="credit_card", include_in_balance=False)
    create_transaction(client, card, "expense", 50_000)
    client.patch(f"{API}/accounts/{left_out['id']}", json={"include_in_balance": False})

    body = wealth(client)

    assert body["available"] == "400000.00"
    assert body["credit_card_debt"] == "0.00"
    listed = {item["name"]: item for item in body["accounts"]}
    assert listed["Savings"]["include_in_balance"] is False
    assert listed["Savings"]["balance"] == "300000.00"
    assert listed["Bank"]["include_in_balance"] is True
