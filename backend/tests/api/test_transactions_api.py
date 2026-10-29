import base64
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import update

from app.db import models
from app.domain.entities import LOCAL_TIMEZONE
from tests.api.helpers import (
    API,
    D,
    add_rate,
    balance_of,
    create_account,
    create_category,
    create_transaction,
    error_code,
    insert_transaction,
)

OCTOBER_15 = "2026-10-15T12:00:00-05:00"


def test_manual_expense_is_confirmed_and_takes_the_account_currency(client):
    bank = create_account(client, initial=1000)

    movement = create_transaction(client, bank, "expense", "250.50", merchant="Tienda", note="Snacks")

    assert movement["status"] == "confirmed"
    assert movement["source"] == "manual"
    assert movement["currency"] == "COP"
    assert movement["amount"] == "250.50"
    assert movement["merchant"] == "Tienda"
    assert movement["target_account_id"] is None
    assert D(client.get(f"{API}/accounts/{bank['id']}").json()["balance"]) == D("749.50")


def test_amounts_have_the_same_format_when_created_and_when_read(client):
    bank = create_account(client, initial=1000)
    assert bank["initial_balance"] == "1000.00"

    created = create_transaction(client, bank, "expense", 100)
    read = client.get(f"{API}/transactions/{created['id']}").json()

    assert created["amount"] == read["amount"] == "100.00"


def test_a_date_without_timezone_is_colombian_time(client):
    bank = create_account(client)

    movement = create_transaction(client, bank, date="2026-10-31T22:00:00")

    saved = datetime.fromisoformat(movement["date"])
    assert saved.utcoffset().total_seconds() == 0 or saved.astimezone(LOCAL_TIMEZONE).hour == 22
    assert saved.astimezone(LOCAL_TIMEZONE).date() == date(2026, 10, 31)


@pytest.mark.parametrize("amount", ["0", "-5", "1.234", "abc"])
def test_amounts_must_be_positive_money(client, amount):
    bank = create_account(client)

    response = client.post(
        f"{API}/transactions", json={"account_id": bank["id"], "type": "expense", "amount": amount}
    )

    assert response.status_code == 422
    assert error_code(response) == "validation_error"


def test_balance_adjustments_have_their_own_endpoint(client):
    bank = create_account(client)

    response = client.post(
        f"{API}/transactions", json={"account_id": bank["id"], "type": "adjustment_in", "amount": "10"}
    )

    assert response.status_code == 422


def test_unknown_account_is_rejected(client):
    response = client.post(
        f"{API}/transactions", json={"account_id": str(uuid.uuid4()), "type": "expense", "amount": "10"}
    )

    assert response.status_code == 422
    assert error_code(response) == "account_not_found"


def test_archived_accounts_do_not_take_new_movements(client):
    bank = create_account(client)
    client.patch(f"{API}/accounts/{bank['id']}", json={"archived": True})

    response = client.post(
        f"{API}/transactions", json={"account_id": bank["id"], "type": "expense", "amount": "10"}
    )

    assert response.status_code == 409
    assert error_code(response) == "account_archived"


def test_category_must_match_the_movement_type(client):
    bank = create_account(client)
    food = create_category(client, "Food", "expense")
    salary = create_category(client, "Salary", "income")

    create_transaction(client, bank, "expense", 10, category_id=food["id"])
    create_transaction(client, bank, "income", 10, category_id=salary["id"])

    wrong = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "expense", "amount": "10", "category_id": salary["id"]},
    )
    assert wrong.status_code == 422
    assert error_code(wrong) == "category_type_mismatch"

    missing = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "expense", "amount": "10", "category_id": str(uuid.uuid4())},
    )
    assert error_code(missing) == "category_not_found"


def test_transfer_fields_are_rejected_on_expenses(client):
    bank = create_account(client)
    other = create_account(client, name="Other")

    response = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "expense", "amount": "10", "target_account_id": other["id"]},
    )

    assert response.status_code == 422
    assert error_code(response) == "transfer_only_field"


def test_transfer_between_own_accounts_moves_money_and_is_an_own_transfer(client):
    bank = create_account(client, initial=1000)
    cash = create_account(client, name="Cash", type="cash")

    movement = create_transaction(client, bank, "transfer", 130, target_account_id=cash["id"])

    assert movement["classification"] == "own_transfer"
    assert movement["target_amount"] is None
    assert balance_of(client, bank) == D("870")
    assert balance_of(client, cash) == D("130")


def test_paying_a_credit_card_is_a_payment_that_reduces_its_debt(client):
    bank = create_account(client, initial=1000)
    card = create_account(client, name="Card", type="credit_card")
    create_transaction(client, card, "expense", 300)

    payment = create_transaction(client, bank, "transfer", 100, target_account_id=card["id"])

    assert payment["classification"] == "payment"
    assert balance_of(client, card) == D("-200")
    assert balance_of(client, bank) == D("900")


def test_lending_and_repaying_go_through_a_loan_account(client):
    bank = create_account(client, initial=1000)
    loan = create_account(client, name="Ana", type="loan", counterparty="Ana")

    lent = create_transaction(client, bank, "transfer", 400, target_account_id=loan["id"])
    repaid = create_transaction(client, loan, "transfer", 150, target_account_id=bank["id"])

    assert lent["classification"] == "loan"
    assert repaid["classification"] == "loan"
    assert balance_of(client, loan) == D("250")
    assert balance_of(client, bank) == D("750")


def test_a_loan_cannot_skip_the_loan_account(client):
    bank = create_account(client, initial=1000)
    cash = create_account(client, name="Cash", type="cash")
    loan = create_account(client, name="Ana", type="loan", counterparty="Ana")

    to_cash = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "transfer", "amount": "10",
              "target_account_id": cash["id"], "classification": "loan"},
    )
    no_target = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "transfer", "amount": "10", "classification": "loan"},
    )
    as_expense = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "transfer", "amount": "10",
              "target_account_id": loan["id"], "classification": "expense"},
    )

    for response in (to_cash, no_target):
        assert response.status_code == 422
        assert error_code(response) == "loan_account_mismatch"

    # Sending money to a loan account as an "expense" is refused by the stricter rule first:
    # an expense never has a destination account.
    assert as_expense.status_code == 422
    assert error_code(as_expense) == "expense_has_no_destination"


def test_transfer_to_the_same_account_is_rejected(client):
    bank = create_account(client)

    response = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "transfer", "amount": "10", "target_account_id": bank["id"]},
    )

    assert response.status_code == 422
    assert error_code(response) == "same_account"


def test_transfer_without_destination_must_say_what_it_was(client):
    bank = create_account(client, initial=1000)

    unclassified = client.post(
        f"{API}/transactions", json={"account_id": bank["id"], "type": "transfer", "amount": "50"}
    )
    assert unclassified.status_code == 422
    assert error_code(unclassified) == "classification_required"
    assert balance_of(client, bank) == D("1000")

    movement = create_transaction(client, bank, "transfer", 50, classification="payment")
    assert movement["classification"] == "payment"
    assert movement["target_account_id"] is None
    assert balance_of(client, bank) == D("950")


def test_a_transfer_to_one_of_my_accounts_is_never_an_expense(client):
    bank = create_account(client, initial=1000)
    other = create_account(client, name="Other")

    response = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "transfer", "amount": "50",
              "target_account_id": other["id"], "classification": "expense"},
    )

    assert response.status_code == 422
    assert error_code(response) == "expense_has_no_destination"


def test_transfers_to_archived_accounts_are_rejected(client):
    bank = create_account(client, initial=1000)
    old = create_account(client, name="Old")
    client.patch(f"{API}/accounts/{old['id']}", json={"archived": True})

    response = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "transfer", "amount": "50", "target_account_id": old["id"]},
    )

    assert response.status_code == 409
    assert error_code(response) == "account_archived"


def test_a_movement_cannot_be_moved_to_an_account_in_another_currency(client):
    cop = create_account(client, name="Pesos", initial=1000)
    usd = create_account(client, name="Dollars", currency="USD", initial=1000)
    movement = create_transaction(client, cop, "expense", 100)

    response = client.patch(f"{API}/transactions/{movement['id']}", json={"account_id": usd["id"]})

    assert response.status_code == 422
    assert error_code(response) == "currency_mismatch"
    assert balance_of(client, usd) == D("1000")


def test_confirming_a_movement_in_another_currency_than_its_account_is_refused(client, db):
    cop = create_account(client, name="Pesos", initial=1000)
    pending = insert_transaction(db, cop["id"], amount="20", currency="USD")

    response = client.post(f"{API}/transactions/{pending}/confirm")

    assert response.status_code == 409
    assert error_code(response) == "currency_mismatch"
    # Nothing was counted, and every balance still works.
    assert balance_of(client, cop) == D("1000")
    assert client.get(f"{API}/accounts").status_code == 200


def test_confirming_a_conversion_without_the_received_amount_is_refused(client, db):
    bank = create_account(client, initial=1_000_000)
    card_usd = create_account(client, name="Card USD", type="credit_card", currency="USD")
    pending = insert_transaction(
        db, bank["id"], type="transfer", amount="400000", target_account_id=card_usd["id"], classification="payment"
    )

    response = client.post(f"{API}/transactions/{pending}/confirm")

    assert response.status_code == 409
    assert error_code(response) == "target_amount_required"


def test_editing_a_conversion_made_without_a_rate_keeps_it(client):
    bank = create_account(client, initial=1_000_000)
    card_usd = create_account(client, name="Card USD", type="credit_card", currency="USD")
    payment = create_transaction(
        client, bank, "transfer", 410_000, target_account_id=card_usd["id"], target_amount="100", date=OCTOBER_15
    )
    url = f"{API}/transactions/{payment['id']}"

    note = client.patch(url, json={"note": "Card payment"})
    moved_date = client.patch(url, json={"date": "2026-10-16T09:00:00-05:00"})

    for response in (note, moved_date):
        assert response.status_code == 200, response.text
        assert D(response.json()["target_amount"]) == D("100")
        assert D(response.json()["fx_rate"]) == D("4100")
    assert balance_of(client, card_usd) == D("100")


def test_changing_the_amount_of_a_conversion_without_a_rate_asks_for_the_received_amount(client):
    bank = create_account(client, initial=1_000_000)
    card_usd = create_account(client, name="Card USD", type="credit_card", currency="USD")
    payment = create_transaction(
        client, bank, "transfer", 410_000, target_account_id=card_usd["id"], target_amount="100", date=OCTOBER_15
    )
    url = f"{API}/transactions/{payment['id']}"

    refused = client.patch(url, json={"amount": "205000"})
    assert refused.status_code == 422
    assert error_code(refused) == "fx_rate_unavailable"

    accepted = client.patch(url, json={"amount": "205000", "target_amount": "50"})
    assert accepted.status_code == 200
    assert D(accepted.json()["target_amount"]) == D("50")
    assert D(accepted.json()["fx_rate"]) == D("4100")


def test_a_cursor_without_timezone_is_rejected(client):
    cursor = base64.urlsafe_b64encode(f"2026-10-15T12:00:00|{uuid.uuid4()}".encode()).decode()

    response = client.get(f"{API}/transactions?cursor={cursor}")

    assert response.status_code == 422
    assert error_code(response) == "invalid_cursor"


def test_transfer_classified_as_expense_uses_expense_categories(client):
    bank = create_account(client)
    plumbing = create_category(client, "Home repairs", "expense")
    transfer_category = create_category(client, "Moves", "transfer")

    movement = create_transaction(
        client, bank, "transfer", 80, classification="expense", category_id=plumbing["id"]
    )
    assert movement["classification"] == "expense"
    assert movement["category_id"] == plumbing["id"]

    wrong = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "transfer", "amount": "80", "classification": "expense",
              "category_id": transfer_category["id"]},
    )
    assert error_code(wrong) == "category_type_mismatch"


def test_cop_to_usd_transfer_uses_the_rate_of_the_day(client, db):
    add_rate(db, date(2026, 10, 14), "4000")
    bank = create_account(client, initial=1_000_000)
    card_usd = create_account(client, name="Card USD", type="credit_card", currency="USD")
    create_transaction(client, card_usd, "expense", 100, date=OCTOBER_15)

    # Oct 15 has no rate of its own: it takes the closest earlier one.
    payment = create_transaction(
        client, bank, "transfer", 400_000, target_account_id=card_usd["id"], date=OCTOBER_15
    )

    assert payment["currency"] == "COP"
    assert D(payment["target_amount"]) == D("100.00")
    assert D(payment["fx_rate"]) == D("4000")
    assert balance_of(client, bank) == D("600000")
    assert balance_of(client, card_usd) == D("0")


def test_usd_to_cop_transfer_multiplies_by_the_rate(client, db):
    add_rate(db, date(2026, 10, 15), "4000")
    bank = create_account(client)
    savings_usd = create_account(client, name="Savings USD", type="savings", currency="USD", initial=100)

    movement = create_transaction(
        client, savings_usd, "transfer", 25, target_account_id=bank["id"], date=OCTOBER_15
    )

    assert D(movement["target_amount"]) == D("100000.00")
    assert balance_of(client, bank) == D("100000")
    assert balance_of(client, savings_usd) == D("75")


def test_explicit_received_amount_sets_the_implied_rate(client):
    bank = create_account(client, initial=1_000_000)
    card_usd = create_account(client, name="Card USD", type="credit_card", currency="USD")

    movement = create_transaction(
        client, bank, "transfer", 410_000, target_account_id=card_usd["id"], target_amount="100"
    )

    assert D(movement["target_amount"]) == D("100")
    assert D(movement["fx_rate"]) == D("4100")


def test_conversion_without_a_rate_asks_for_the_received_amount(client):
    bank = create_account(client, initial=1_000_000)
    card_usd = create_account(client, name="Card USD", type="credit_card", currency="USD")

    response = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "transfer", "amount": "400000",
              "target_account_id": card_usd["id"], "date": "2001-01-01T12:00:00-05:00"},
    )

    assert response.status_code == 422
    assert error_code(response) == "fx_rate_unavailable"


def test_received_amount_only_applies_between_different_currencies(client):
    bank = create_account(client, initial=1000)
    cash = create_account(client, name="Cash", type="cash")

    response = client.post(
        f"{API}/transactions",
        json={"account_id": bank["id"], "type": "transfer", "amount": "10",
              "target_account_id": cash["id"], "target_amount": "10"},
    )

    assert response.status_code == 422
    assert error_code(response) == "target_amount_not_allowed"


def test_list_is_newest_first_and_filters_combine(client):
    bank = create_account(client)
    cash = create_account(client, name="Cash", type="cash")
    food = create_category(client, "Food", "expense")
    old = create_transaction(client, bank, "expense", 1, date="2026-09-01T10:00:00-05:00", merchant="Old shop")
    mid = create_transaction(client, bank, "expense", 2, date="2026-10-10T10:00:00-05:00", category_id=food["id"])
    income = create_transaction(client, bank, "income", 3, date="2026-10-20T10:00:00-05:00")
    moved = create_transaction(
        client, bank, "transfer", 4, date="2026-10-25T10:00:00-05:00", target_account_id=cash["id"]
    )

    def ids(query: str) -> list[str]:
        response = client.get(f"{API}/transactions?{query}")
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    assert ids("") == [moved["id"], income["id"], mid["id"], old["id"]]
    assert ids("type=expense") == [mid["id"], old["id"]]
    assert ids(f"category_id={food['id']}") == [mid["id"]]
    assert ids(f"account_id={cash['id']}") == [moved["id"]]
    assert ids("from=2026-10-01&to=2026-10-20") == [income["id"], mid["id"]]
    assert ids("q=old%20SHOP") == [old["id"]]
    assert ids("status=pending_review") == []


def test_date_filters_use_colombian_days(client):
    bank = create_account(client)
    late = create_transaction(client, bank, date="2026-10-31T23:30:00-05:00")
    next_day = create_transaction(client, bank, date="2026-11-01T00:30:00-05:00")

    response = client.get(f"{API}/transactions?from=2026-10-01&to=2026-10-31")
    found = [item["id"] for item in response.json()["items"]]

    assert late["id"] in found
    assert next_day["id"] not in found


def test_text_search_treats_wildcards_as_plain_text(client):
    bank = create_account(client)
    percent = create_transaction(client, bank, merchant="100% juice")
    plain = create_transaction(client, bank, merchant="1000 juice")

    found = [item["id"] for item in client.get(f"{API}/transactions?q=100%25").json()["items"]]

    assert found == [percent["id"]]
    assert plain["id"] not in found


def test_pagination_walks_every_movement_once(client):
    bank = create_account(client)
    created = [
        create_transaction(client, bank, "expense", 1 + index, date=f"2026-10-{10 + index:02d}T10:00:00-05:00")["id"]
        for index in range(5)
    ]
    # Two movements at the exact same instant must still page without gaps or repeats.
    created.append(create_transaction(client, bank, "expense", 9, date="2026-10-14T10:00:00-05:00")["id"])

    seen, cursor = [], None
    for _ in range(10):
        query = f"{API}/transactions?limit=2&account_id={bank['id']}" + (f"&cursor={cursor}" if cursor else "")
        page = client.get(query).json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert sorted(seen) == sorted(created)
    assert len(seen) == len(set(seen)) == 6


def test_bad_cursor_and_limits_are_validation_errors(client):
    bad_cursor = client.get(f"{API}/transactions?cursor=garbage")
    assert bad_cursor.status_code == 422
    assert error_code(bad_cursor) == "invalid_cursor"

    assert client.get(f"{API}/transactions?limit=0").status_code == 422
    assert client.get(f"{API}/transactions?limit=1000").status_code == 422


def test_update_amount_and_text_fields_and_balance_follows(client):
    bank = create_account(client, initial=1000)
    movement = create_transaction(client, bank, "expense", 100)

    response = client.patch(
        f"{API}/transactions/{movement['id']}", json={"amount": "250", "merchant": "Corrected", "note": None}
    )

    assert response.status_code == 200
    assert response.json()["merchant"] == "Corrected"
    assert response.json()["amount"] == "250.00"
    assert balance_of(client, bank) == D("750")


def test_update_can_move_a_movement_to_another_account(client):
    first = create_account(client, name="First", initial=1000)
    second = create_account(client, name="Second", initial=1000)
    movement = create_transaction(client, first, "expense", 100)

    client.patch(f"{API}/transactions/{movement['id']}", json={"account_id": second["id"]})

    assert balance_of(client, first) == D("1000")
    assert balance_of(client, second) == D("900")


def test_update_rejects_what_cannot_change(client):
    bank = create_account(client)
    movement = create_transaction(client, bank)
    url = f"{API}/transactions/{movement['id']}"

    assert client.patch(url, json={"type": "income"}).status_code == 422
    assert client.patch(url, json={"status": "discarded"}).status_code == 422
    assert client.patch(url, json={"amount": None}).status_code == 422
    assert client.patch(url, json={"amount": "-1"}).status_code == 422


def test_editing_text_keeps_the_stored_conversion(client, db):
    add_rate(db, date(2026, 10, 15), "4000")
    bank = create_account(client, initial=1_000_000)
    card_usd = create_account(client, name="Card USD", type="credit_card", currency="USD")
    payment = create_transaction(
        client, bank, "transfer", 400_000, target_account_id=card_usd["id"], date=OCTOBER_15
    )
    # The rate is corrected afterwards, but the stored movement must not move.
    db.execute(update(models.FxRate).values(value=D("9999")))
    db.commit()

    edited = client.patch(f"{API}/transactions/{payment['id']}", json={"note": "Card payment"}).json()

    assert edited["note"] == "Card payment"
    assert D(edited["target_amount"]) == D("100.00")
    assert D(edited["fx_rate"]) == D("4000")


def test_changing_the_amount_of_a_conversion_recomputes_it(client, db):
    add_rate(db, date(2026, 10, 15), "4000")
    bank = create_account(client, initial=1_000_000)
    card_usd = create_account(client, name="Card USD", type="credit_card", currency="USD")
    payment = create_transaction(
        client, bank, "transfer", 400_000, target_account_id=card_usd["id"], date=OCTOBER_15
    )

    edited = client.patch(f"{API}/transactions/{payment['id']}", json={"amount": "200000"}).json()

    assert D(edited["target_amount"]) == D("50.00")


def test_changing_the_destination_resets_the_classification(client):
    bank = create_account(client, initial=1000)
    cash = create_account(client, name="Cash", type="cash")
    card = create_account(client, name="Card", type="credit_card")
    movement = create_transaction(client, bank, "transfer", 100, target_account_id=cash["id"])
    assert movement["classification"] == "own_transfer"

    edited = client.patch(f"{API}/transactions/{movement['id']}", json={"target_account_id": card["id"]}).json()

    assert edited["classification"] == "payment"


def test_manual_movement_can_be_deleted(client):
    bank = create_account(client, initial=1000)
    movement = create_transaction(client, bank, "expense", 100)

    assert client.delete(f"{API}/transactions/{movement['id']}").status_code == 204
    assert client.get(f"{API}/transactions/{movement['id']}").status_code == 404
    assert balance_of(client, bank) == D("1000")


def test_automatic_movement_cannot_be_deleted_only_discarded(client, db):
    bank = create_account(client)
    automatic = insert_transaction(db, bank["id"], source="gmail", status="confirmed")

    response = client.delete(f"{API}/transactions/{automatic}")

    assert response.status_code == 409
    assert error_code(response) == "use_discard"


def test_pending_movements_do_not_count_until_confirmed(client, db):
    bank = create_account(client, initial=1000)
    pending = insert_transaction(db, bank["id"], amount="300")

    assert balance_of(client, bank) == D("1000")

    confirmed = client.post(f"{API}/transactions/{pending}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert balance_of(client, bank) == D("700")

    again = client.post(f"{API}/transactions/{pending}/confirm")
    assert again.status_code == 409
    assert error_code(again) == "not_pending"


def test_discarded_movements_never_count(client, db):
    bank = create_account(client, initial=1000)
    pending = insert_transaction(db, bank["id"], amount="300")

    discarded = client.post(f"{API}/transactions/{pending}/discard")
    assert discarded.status_code == 200
    assert discarded.json()["status"] == "discarded"
    assert balance_of(client, bank) == D("1000")

    again = client.post(f"{API}/transactions/{pending}/discard")
    assert again.status_code == 409
    assert error_code(again) == "already_discarded"

    cannot_confirm = client.post(f"{API}/transactions/{pending}/confirm")
    assert cannot_confirm.status_code == 409


def test_discarded_movements_are_not_listed_unless_asked_for(client, db):
    bank = create_account(client, initial=1000)
    kept = create_transaction(client, bank, "expense", 100)
    pending = insert_transaction(db, bank["id"], amount="300")
    client.post(f"{API}/transactions/{pending}/discard")

    everything = client.get(f"{API}/transactions").json()["items"]
    discarded = client.get(f"{API}/transactions", params={"status": "discarded"}).json()["items"]

    assert [item["id"] for item in everything] == [kept["id"]]
    assert [item["id"] for item in discarded] == [pending]
    searched = client.get(f"{API}/transactions", params={"account_id": bank["id"]}).json()["items"]
    assert [item["id"] for item in searched] == [kept["id"]]


def test_a_confirmed_movement_can_be_discarded_and_stops_counting(client):
    bank = create_account(client, initial=1000)
    movement = create_transaction(client, bank, "expense", 100)

    client.post(f"{API}/transactions/{movement['id']}/discard")

    assert balance_of(client, bank) == D("1000")


def test_unknown_movement_is_not_found(client):
    for method, path in (
        ("get", ""),
        ("patch", ""),
        ("delete", ""),
        ("post", "/confirm"),
        ("post", "/discard"),
    ):
        response = getattr(client, method)(f"{API}/transactions/{uuid.uuid4()}{path}", **(
            {"json": {"note": "x"}} if method == "patch" else {}
        ))
        assert response.status_code == 404, f"{method} {path}"
        assert error_code(response) == "not_found"
