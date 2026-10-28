from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db import models
from app.domain.entities import LOCAL_TIMEZONE
from app.parsers.bancolombia import parse_bancolombia
from app.parsers.uala_sms import parse_uala_sms
from app.services import ingest
from app.services.ingest import Outcome
from tests.api.helpers import API, create_account, error_code

D = Decimal
RECEIVED = datetime(2026, 10, 27, 15, 0, tzinfo=LOCAL_TIMEZONE)

PURCHASE = "Bancolombia: Compraste COP12.300,00 en TIENDA EJEMPLO con tu T.Cred *1234, el 05/03/2026 a las 14:25."
PURCHASE_USD = "Bancolombia: Compraste USD10,00 en TIENDA EJEMPLO con tu T.Cred *1234, el 05/03/2026 a las 14:25."
TRANSFER_OUT_PERSON = (
    "Bancolombia: transferiste $50.000 a la llave @ejemplo desde tu cuenta *1234 a Persona Ejemplo "
    "el 05/03/2026 a las 10:00."
)
TRANSFER_OUT_OWN = "Bancolombia: Transferiste $50.000 desde tu cuenta *1234 a la cuenta *5678, el 05/03/2026 a las 10:00."
TRANSFER_IN = "Bancolombia: Recibiste una transferencia por $100.000 de Persona Ejemplo en tu cuenta *1234, el 05/03/2026 a las 11:00."
PAYROLL = "Bancolombia: Recibiste un pago de Nómina de EMPRESA EJEMPLO por $2.000.000 en tu cuenta de Ahorros el 05/03/2026 a las 08:00."
WITHDRAWAL = "Bancolombia: Retiraste $100.000 en CAJERO EJEMPLO 1 de tu T.Deb **1234 el 05/03/2026 a las 12:00."
FAILED = "Bancolombia: Tu compra por $5.000 en TIENDA EJEMPLO no fue exitosa, el 05/03/2026 a las 14:25."
UALA_PAYMENT = "Ualá Pagaste $50000 en TIENDA EJEMPLO MEDELLIN COL 🏦"
UALA_TOP_UP = "¡Tu recarga por PSE está lista! 💰 Realizaste una recarga por $250000 a tu cuenta Ualá."
UALA_YIELD = "Ualá Devolvimos $10000.00 a tu Ualá 💸"


def bank(text):
    return parse_bancolombia(text)


def with_digits(client, account, digits, kind="credit"):
    response = client.put(f"{API}/accounts/{account['id']}/identifiers", json={"identifiers": [{"digits": digits, "type": kind}]})
    assert response.status_code == 200, response.text
    return account


def rows(db):
    return list(db.scalars(select(models.Transaction)))


@pytest.fixture
def card(client):
    return with_digits(client, create_account(client, name="Card", type="credit_card"), "1234")


def test_a_purchase_is_stored_as_pending_on_the_account_of_its_card(db, card):
    result = ingest.ingest(db, bank(PURCHASE))

    assert result.outcome is Outcome.CREATED
    row = result.transaction
    assert (str(row.account_id), row.type, row.amount, row.currency) == (card["id"], "expense", D("12300"), "COP")
    assert (row.merchant, row.source, row.status) == ("TIENDA EJEMPLO", "gmail", "pending_review")
    assert row.dedupe_hash and row.target_account_id is None and row.classification is None


def test_a_pending_movement_counts_nowhere_until_it_is_confirmed(client, db, card):
    result = ingest.ingest(db, bank(PURCHASE))
    assert client.get(f"{API}/accounts/{card['id']}").json()["balance"] == "0.00"

    response = client.post(f"{API}/transactions/{result.transaction.id}/confirm")

    assert response.status_code == 200, response.text
    assert client.get(f"{API}/accounts/{card['id']}").json()["balance"] == "-12300.00"


def test_the_same_notification_twice_is_stored_once(db, card):
    first = ingest.ingest(db, bank(PURCHASE))
    second = ingest.ingest(db, bank(PURCHASE))

    assert (first.outcome, second.outcome) == (Outcome.CREATED, Outcome.DUPLICATE)
    assert second.transaction.id == first.transaction.id
    assert len(rows(db)) == 1


def test_losing_a_race_for_the_same_notification_is_a_duplicate_too(db, card, monkeypatch):
    first = ingest.ingest(db, bank(PURCHASE))
    real = ingest._by_hash
    calls = []
    monkeypatch.setattr(ingest, "_by_hash", lambda session, digest: calls.append(1) or (None if len(calls) == 1 else real(session, digest)))

    second = ingest.ingest(db, bank(PURCHASE))

    assert second.outcome is Outcome.DUPLICATE and second.transaction.id == first.transaction.id
    assert len(rows(db)) == 1


def test_what_is_not_a_movement_or_not_recognized_stores_nothing(db, card):
    assert ingest.ingest(db, bank(FAILED)).outcome is Outcome.IGNORED
    assert ingest.ingest(db, None).outcome is Outcome.UNRECOGNIZED
    assert rows(db) == []


def test_digits_that_belong_to_no_account_leave_the_account_empty_and_it_cannot_be_confirmed(client, db):
    result = ingest.ingest(db, bank(PURCHASE))

    assert result.outcome is Outcome.CREATED and result.transaction.account_id is None
    response = client.post(f"{API}/transactions/{result.transaction.id}/confirm")
    assert response.status_code == 409 and error_code(response) == "account_required"
    other = create_account(client, name="Other", type="credit_card")

    assigned = client.patch(f"{API}/transactions/{result.transaction.id}", json={"account_id": other["id"]})

    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["account_id"] == other["id"]
    assert client.post(f"{API}/transactions/{result.transaction.id}/confirm").status_code == 200


def test_a_movement_without_account_cannot_be_edited_before_choosing_one(client, db):
    result = ingest.ingest(db, bank(PURCHASE))

    response = client.patch(f"{API}/transactions/{result.transaction.id}", json={"note": "x"})

    assert response.status_code == 409 and error_code(response) == "account_required"


def test_the_same_digits_in_another_currency_pick_the_account_of_that_currency(client, db, card):
    usd = with_digits(client, create_account(client, name="Card USD", type="credit_card", currency="USD"), "1234")

    cop_row = ingest.ingest(db, bank(PURCHASE)).transaction
    usd_row = ingest.ingest(db, bank(PURCHASE_USD)).transaction

    assert (str(cop_row.account_id), str(usd_row.account_id)) == (card["id"], usd["id"])
    assert usd_row.currency == "USD"


def test_digits_shared_by_two_accounts_of_a_currency_assume_neither(client, db, card):
    twin = create_account(client, name="Twin", type="credit_card")
    # The API refuses this, but the database does not: a notification must still not pick one of them.
    db.add(models.AccountIdentifier(account_id=twin["id"], digits="1234", type="credit"))
    db.commit()

    assert ingest.ingest(db, bank(PURCHASE)).transaction.account_id is None


def test_a_transfer_to_a_person_waits_for_a_class_and_cannot_be_confirmed_without_it(client, db, card):
    row = ingest.ingest(db, bank(TRANSFER_OUT_PERSON)).transaction

    assert (row.type, row.classification, row.target_account_id, row.target_text) == ("transfer", None, None, "Persona Ejemplo")
    response = client.post(f"{API}/transactions/{row.id}/confirm")
    assert response.status_code == 409 and error_code(response) == "classification_required"


def test_a_transfer_to_the_digits_of_an_own_account_is_an_own_transfer(client, db, card):
    savings = with_digits(client, create_account(client, name="Savings", type="savings"), "5678", "account")

    row = ingest.ingest(db, bank(TRANSFER_OUT_OWN)).transaction

    assert (row.type, str(row.target_account_id), row.classification, row.target_text) == ("transfer", savings["id"], "own_transfer", None)


def test_money_received_is_an_income_on_the_account_of_its_digits(client, db, card):
    row = ingest.ingest(db, bank(TRANSFER_IN)).transaction

    assert (row.type, str(row.account_id), row.merchant) == ("income", card["id"], "Persona Ejemplo")


def test_a_payroll_goes_to_the_only_savings_account(client, db):
    savings = create_account(client, name="Savings", type="savings")

    row = ingest.ingest(db, bank(PAYROLL)).transaction

    assert (row.type, str(row.account_id)) == ("income", savings["id"])


def test_a_payroll_with_two_savings_accounts_assumes_neither(client, db):
    create_account(client, name="Savings", type="savings")
    create_account(client, name="Savings 2", type="savings")

    assert ingest.ingest(db, bank(PAYROLL)).transaction.account_id is None


def test_a_withdrawal_is_a_transfer_to_the_cash_account(client, db):
    debit = with_digits(client, create_account(client, name="Bank", type="bank"), "1234", "debit")
    cash = create_account(client, name="Cash", type="cash")

    row = ingest.ingest(db, bank(WITHDRAWAL)).transaction

    assert (row.type, str(row.account_id), str(row.target_account_id), row.classification) == (
        "transfer", debit["id"], cash["id"], "own_transfer",
    )


def test_an_uala_payment_goes_to_the_only_wallet(client, db):
    wallet = create_account(client, name="Wallet", type="wallet")

    result = ingest.ingest(db, parse_uala_sms(UALA_PAYMENT, RECEIVED))

    assert (result.transaction.type, str(result.transaction.account_id), result.transaction.source) == ("expense", wallet["id"], "sms_uala")


def test_a_top_up_enters_the_wallet_from_an_account_to_be_chosen(client, db):
    wallet = create_account(client, name="Wallet", type="wallet")

    row = ingest.ingest(db, parse_uala_sms(UALA_TOP_UP, RECEIVED)).transaction

    assert (row.type, row.account_id, str(row.target_account_id), row.classification) == ("transfer", None, wallet["id"], "own_transfer")


def test_the_daily_return_of_the_wallet_takes_its_category_when_there_is_one(client, db):
    create_account(client, name="Wallet", type="wallet")
    category = client.post(f"{API}/categories", json={"name": "Rendimientos", "type": "income"}).json()

    row = ingest.ingest(db, parse_uala_sms(UALA_YIELD, RECEIVED)).transaction

    assert (row.type, str(row.category_id)) == ("income", category["id"])


def test_a_text_without_an_amount_or_a_day_is_not_stored(db, card):
    parsed = bank(PURCHASE)
    from dataclasses import replace

    assert ingest.ingest(db, replace(parsed, amount=None)).outcome is Outcome.UNRECOGNIZED
    assert ingest.ingest(db, replace(parsed, occurred_at=None, occurred_on=None)).outcome is Outcome.UNRECOGNIZED
    assert ingest.ingest(db, replace(parsed, currency=None)).outcome is Outcome.UNRECOGNIZED
    assert rows(db) == []


def test_the_pending_list_of_the_api_shows_what_was_ingested(client, db, card):
    ingest.ingest(db, bank(PURCHASE))
    ingest.ingest(db, bank(TRANSFER_OUT_PERSON))

    body = client.get(f"{API}/transactions", params={"status": "pending_review"}).json()

    assert len(body["items"]) == 2
    assert db.scalar(select(func.count()).select_from(models.Transaction)) == 2
