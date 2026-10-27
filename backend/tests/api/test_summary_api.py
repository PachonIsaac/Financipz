from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, event

from app.db import models

from tests.api.helpers import (
    API,
    add_rate,
    create_account,
    create_category,
    create_transaction,
    error_code,
    insert_transaction,
)

D = Decimal


def summary(client, month: str | None = "2026-10"):
    return client.get(f"{API}/summary", params={"month": month} if month else {})


def test_empty_database_gives_zeros_and_a_six_month_trend(client):
    response = summary(client)

    assert response.status_code == 200
    body = response.json()
    assert body["month"] == "2026-10"
    assert (body["income"], body["expenses"], body["balance"]) == ("0.00", "0.00", "0.00")
    assert body["income_by_category"] == []
    assert body["expenses_by_category"] == []
    assert [item["month"] for item in body["trend"]] == [
        "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10",
    ]
    assert all(item["income"] == "0.00" for item in body["trend"])


def test_totals_and_categories_of_the_month(client):
    bank = create_account(client)
    food = create_category(client, "Food", color="#ff8800")
    pay = create_category(client, "Salary", "income", color="#00aa00")
    create_transaction(client, bank, "income", 1_000_000, date="2026-10-01T09:00:00-05:00", category_id=pay["id"])
    create_transaction(client, bank, "expense", 200_000, date="2026-10-05T09:00:00-05:00", category_id=food["id"])
    create_transaction(client, bank, "expense", 50_000, date="2026-10-06T09:00:00-05:00", category_id=food["id"])
    create_transaction(client, bank, "expense", 30_000.5, date="2026-10-07T09:00:00-05:00")

    body = summary(client).json()

    assert body["income"] == "1000000.00"
    assert body["expenses"] == "280000.50"
    assert body["balance"] == "719999.50"
    assert body["income_by_category"] == [
        {"category_id": pay["id"], "name": "Salary", "color": "#00aa00", "amount": "1000000.00"}
    ]
    # Largest first, and movements without a category are grouped under a null id.
    assert body["expenses_by_category"] == [
        {"category_id": food["id"], "name": "Food", "color": "#ff8800", "amount": "250000.00"},
        {"category_id": None, "name": "Sin categoría", "color": None, "amount": "30000.50"},
    ]


def test_only_confirmed_flow_movements_count(client, db):
    bank = create_account(client, name="Bank")
    savings = create_account(client, name="Savings", type="savings")
    create_transaction(client, bank, "expense", 10_000, date="2026-10-05T09:00:00-05:00")
    create_transaction(client, bank, "transfer", 500_000, target_account_id=savings["id"],
                       date="2026-10-05T09:00:00-05:00")
    # A transfer that leaves for good (no destination account of mine) classified as an expense counts.
    create_transaction(client, bank, "transfer", 7_000, classification="expense",
                       date="2026-10-05T09:00:00-05:00")
    insert_transaction(db, bank["id"], amount="99999", status="pending_review")
    insert_transaction(db, bank["id"], amount="88888", status="discarded")

    body = summary(client).json()

    assert body["expenses"] == "17000.00"
    assert body["income"] == "0.00"


def test_negative_balance_when_expenses_exceed_income(client):
    bank = create_account(client)
    create_transaction(client, bank, "income", 100_000, date="2026-10-02T09:00:00-05:00")
    create_transaction(client, bank, "expense", 350_000, date="2026-10-03T09:00:00-05:00")

    assert summary(client).json()["balance"] == "-250000.00"


def test_month_boundary_follows_colombian_time(client):
    bank = create_account(client)
    # 23:30 in Colombia on Oct 31 is already November 1 in UTC: it belongs to October.
    create_transaction(client, bank, "expense", 1_000, date="2026-10-31T23:30:00-05:00")
    # One hour later is November in Colombia too.
    create_transaction(client, bank, "expense", 2_000, date="2026-11-01T00:30:00-05:00")
    # Written in UTC, 04:30 on Nov 1 is still Oct 31 at 23:30 in Colombia.
    create_transaction(client, bank, "expense", 400, date="2026-11-01T04:30:00+00:00")

    october = summary(client, "2026-10").json()
    november = summary(client, "2026-11").json()

    assert october["expenses"] == "1400.00"
    assert november["expenses"] == "2000.00"


def test_trend_has_the_totals_of_each_month_oldest_first(client):
    bank = create_account(client)
    create_transaction(client, bank, "expense", 100, date="2026-05-10T10:00:00-05:00")
    create_transaction(client, bank, "income", 900, date="2026-07-10T10:00:00-05:00")
    create_transaction(client, bank, "expense", 300, date="2026-10-10T10:00:00-05:00")
    # Outside the window: too old and in the future.
    create_transaction(client, bank, "expense", 5, date="2026-04-30T10:00:00-05:00")
    create_transaction(client, bank, "expense", 7, date="2026-11-02T10:00:00-05:00")

    trend = summary(client).json()["trend"]

    assert [(item["month"], item["income"], item["expenses"], item["balance"]) for item in trend] == [
        ("2026-05", "0.00", "100.00", "-100.00"),
        ("2026-06", "0.00", "0.00", "0.00"),
        ("2026-07", "900.00", "0.00", "900.00"),
        ("2026-08", "0.00", "0.00", "0.00"),
        ("2026-09", "0.00", "0.00", "0.00"),
        ("2026-10", "0.00", "300.00", "-300.00"),
    ]


def test_trend_crosses_the_year(client):
    body = summary(client, "2026-02").json()

    assert [item["month"] for item in body["trend"]] == [
        "2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
    ]


def test_usd_movements_use_the_rate_of_their_day_or_the_closest_earlier(client, db):
    add_rate(db, date(2026, 10, 2), "4000")
    add_rate(db, date(2026, 10, 9), "4100")
    card = create_account(client, name="Card USD", type="credit_card", currency="USD")
    # A Sunday: uses the Friday rate.
    create_transaction(client, card, "expense", 10, date="2026-10-04T12:00:00-05:00")
    create_transaction(client, card, "expense", 20, date="2026-10-09T12:00:00-05:00")

    body = summary(client).json()

    assert body["expenses"] == "122000.00"


def test_usd_movement_without_any_rate_is_a_clear_error(client, db):
    add_rate(db, date(2026, 10, 1), "4000")
    card = create_account(client, name="Card USD", type="credit_card", currency="USD")
    create_transaction(client, card, "expense", 10, date="2026-10-04T12:00:00-05:00")
    db.execute(delete(models.FxRate))
    db.commit()

    response = summary(client)

    assert response.status_code == 409
    assert error_code(response) == "missing_fx_rate"


@pytest.mark.parametrize("month", ["2026-13", "2026-00", "2026-1", "26-10", "october", "2026-10-01", "2026/10", "", "9999-12", "0001-03", "1999-12"])
def test_bad_month_is_rejected(client, month):
    response = client.get(f"{API}/summary", params={"month": month})

    assert response.status_code == 422
    assert error_code(response) == "invalid_month"
    assert "AAAA-MM" in response.json()["error"]["message"]


def test_default_month_is_the_current_one_in_colombia(client, monkeypatch):
    monkeypatch.setattr("app.services.summary.local_today", lambda: date(2027, 1, 15))

    assert summary(client, None).json()["month"] == "2027-01"


def test_few_queries_whatever_the_number_of_months(client, connection):
    bank = create_account(client)
    create_transaction(client, bank, "expense", 10, date="2026-10-05T09:00:00-05:00")
    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(connection.engine, "before_cursor_execute", count)
    try:
        assert summary(client).status_code == 200
    finally:
        event.remove(connection.engine, "before_cursor_execute", count)

    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 4


def test_adjustments_and_exchange_accounts_stay_out_of_the_flow(client):
    bank = create_account(client, name="Bank", initial=100_000)
    exchange = create_account(client, name="Exchange", type="exchange")
    create_transaction(client, bank, "expense", 10_000, date="2026-10-05T09:00:00-05:00")
    create_transaction(client, exchange, "income", 777_000, date="2026-10-05T09:00:00-05:00")
    create_transaction(client, exchange, "expense", 555, date="2026-10-05T09:00:00-05:00")
    adjusted_up = client.post(
        f"{API}/accounts/{bank['id']}/adjustments", json={"observed_balance": "500000", "note": "count"}
    )
    adjusted_down = client.post(
        f"{API}/accounts/{bank['id']}/adjustments", json={"observed_balance": "1000", "note": "count"}
    )
    assert adjusted_up.status_code == 201 and adjusted_down.status_code == 201

    body = summary(client).json()

    assert body["income"] == "0.00"
    assert body["expenses"] == "10000.00"
