import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db import models
from app.domain.entities import LOCAL_TIMEZONE
from app.services import ingest
from tests.api.helpers import API, balance_of, create_account, create_transaction, error_code, insert_transaction
from tests.api.test_ingest import TRANSFER_OUT_PERSON, bank, with_digits

D = Decimal
NOON = datetime(2026, 10, 15, 12, 0, tzinfo=LOCAL_TIMEZONE)


def matches(client, transaction_id):
    response = client.get(f"{API}/transactions/{transaction_id}/matches")
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()]


def merge(client, absorbed, into):
    return client.post(f"{API}/transactions/{absorbed}/merge", json={"into": into})


def manual(client, account, amount, when="2026-10-15T12:00:00-05:00", **extra):
    return create_transaction(client, account, "expense", amount, date=when, **extra)["id"]


@pytest.fixture
def bank_account(client):
    return create_account(client, name="Bank", type="bank", initial=1_000_000)


def test_the_same_amount_from_another_source_within_a_day_is_a_candidate(client, db, bank_account):
    typed = manual(client, bank_account, 86_400)
    announced = insert_transaction(db, bank_account["id"], amount="86400", when=NOON + timedelta(hours=5))

    assert matches(client, announced) == [typed]


@pytest.mark.parametrize(
    "case",
    [
        "other_amount",
        "two_days_away",
        "same_source",
        "discarded",
        "other_currency",
    ],
)
def test_what_does_not_look_like_the_same_movement_is_not_offered(client, db, bank_account, case):
    announced = insert_transaction(db, bank_account["id"], amount="86400")
    usd = create_account(client, name="Dollars", type="bank", currency="USD")
    if case == "other_amount":
        manual(client, bank_account, 86_401)
    elif case == "two_days_away":
        manual(client, bank_account, 86_400, when="2026-10-17T13:00:00-05:00")
    elif case == "same_source":
        insert_transaction(db, bank_account["id"], amount="86400", source="gmail")
    elif case == "discarded":
        other = manual(client, bank_account, 86_400)
        client.post(f"{API}/transactions/{other}/discard")
    elif case == "other_currency":
        create_transaction(client, usd, "expense", 86_400, date="2026-10-15T12:00:00-05:00")

    assert matches(client, announced) == []


def test_only_a_pending_movement_has_candidates_and_the_closest_comes_first(client, db, bank_account):
    far = manual(client, bank_account, 5_000, when="2026-10-15T20:00:00-05:00")
    near = manual(client, bank_account, 5_000, when="2026-10-15T12:30:00-05:00")
    announced = insert_transaction(db, bank_account["id"], amount="5000")

    assert matches(client, announced) == [near, far]
    assert matches(client, near) == []


def test_saying_it_is_the_same_keeps_the_typed_one_and_sets_the_announced_one_aside(client, db, bank_account):
    typed = manual(client, bank_account, 86_400)
    announced_row = models.Transaction(
        id=uuid.uuid4(), account_id=uuid.UUID(bank_account["id"]), type="expense", amount=D("86400"), currency="COP",
        date=NOON, merchant="SUPERMERCADO", source="gmail", status="pending_review", dedupe_hash="hash-1",
    )
    db.add(announced_row)
    db.commit()
    before = balance_of(client, bank_account)

    response = merge(client, announced_row.id, typed)

    assert response.status_code == 200, response.text
    assert response.json()["id"] == typed and response.json()["merchant"] == "SUPERMERCADO"
    db.expire_all()
    assert db.get(models.Transaction, announced_row.id).status == "discarded"
    assert db.get(models.Transaction, announced_row.id).dedupe_hash == "hash-1"
    assert balance_of(client, bank_account) == before
    listed = [item["id"] for item in client.get(f"{API}/transactions").json()["items"]]
    assert str(announced_row.id) not in listed


def test_what_the_kept_movement_already_has_is_never_replaced(client, db, bank_account):
    typed = manual(client, bank_account, 300, merchant="Mi nombre")
    other_account = create_account(client, name="Other", type="bank")
    announced = insert_transaction(db, other_account["id"], amount="300")
    db.get(models.Transaction, uuid.UUID(announced)).merchant = "SU NOMBRE"
    db.commit()

    kept = merge(client, announced, typed).json()

    assert (kept["merchant"], kept["account_id"]) == ("Mi nombre", bank_account["id"])


def test_the_two_notices_of_one_own_transfer_become_a_single_transfer(client, db):
    bank_account = with_digits(client, create_account(client, name="Bank", type="bank", initial=1_000_000), "1234", "account")
    wallet = create_account(client, name="Wallet", type="wallet")
    out = insert_transaction(db, bank_account["id"], type="transfer", amount="250000", source="gmail")
    out_row = db.get(models.Transaction, uuid.UUID(out))
    out_row.target_text = "UALA"
    top_up = models.Transaction(
        id=uuid.uuid4(), account_id=None, target_account_id=uuid.UUID(wallet["id"]), classification="own_transfer",
        type="transfer", amount=D("250000"), currency="COP", date=NOON + timedelta(minutes=2), source="sms_uala",
        status="pending_review",
    )
    db.add(top_up)
    db.commit()
    assert matches(client, str(top_up.id)) == [out]

    kept = merge(client, top_up.id, out).json()

    assert (kept["account_id"], kept["target_account_id"], kept["classification"], kept["target_text"]) == (
        bank_account["id"], wallet["id"], "own_transfer", None,
    )
    assert client.post(f"{API}/transactions/{out}/confirm").status_code == 200
    assert balance_of(client, bank_account) == D("750000")
    assert balance_of(client, wallet) == D("250000")


def test_a_wrong_request_to_merge_is_refused_and_changes_nothing(client, db, bank_account):
    typed = manual(client, bank_account, 100)
    announced = insert_transaction(db, bank_account["id"], amount="100")
    different = insert_transaction(db, bank_account["id"], amount="101", source="sms_uala")
    set_aside = insert_transaction(db, bank_account["id"], amount="100", source="sms_uala", status="discarded")

    assert error_code(merge(client, announced, announced)) == "same_movement"
    assert error_code(merge(client, typed, announced)) == "not_pending"
    assert error_code(merge(client, announced, different)) == "not_the_same_amount"
    assert error_code(merge(client, announced, set_aside)) == "already_discarded"
    assert merge(client, announced, str(uuid.uuid4())).status_code == 404
    assert merge(client, str(uuid.uuid4()), typed).status_code == 404
    assert db.get(models.Transaction, uuid.UUID(announced)).status == "pending_review"


def test_a_transfer_to_the_key_of_one_of_my_accounts_is_an_own_transfer_whatever_the_case(client, db):
    card = with_digits(client, create_account(client, name="Bank", type="bank"), "1234", "account")
    wallet = create_account(client, name="Wallet", type="wallet", key="@EJEMPLO")

    row = ingest.ingest(db, bank(TRANSFER_OUT_PERSON)).transaction

    assert (str(row.account_id), str(row.target_account_id), row.classification) == (card["id"], wallet["id"], "own_transfer")
    # The name the notice gave stays, so the reviewer sees where it said the money went.
    assert row.target_text is None or row.target_text == "Persona Ejemplo"
    assert list(db.scalars(select(models.Transaction))) == [row]


def test_joining_never_moves_money_on_a_movement_that_already_counts(client, db):
    savings = create_account(client, name="Savings", type="savings", initial=1_000_000)
    wallet = create_account(client, name="Wallet", type="wallet")
    typed = client.post(
        f"{API}/transactions",
        json={"account_id": savings["id"], "type": "transfer", "amount": "40000", "classification": "expense"},
    ).json()["id"]
    notice = models.Transaction(
        id=uuid.uuid4(), account_id=uuid.UUID(savings["id"]), target_account_id=uuid.UUID(wallet["id"]),
        classification="own_transfer", type="transfer", amount=D("40000"), currency="COP",
        date=datetime.now(LOCAL_TIMEZONE), source="gmail", status="pending_review", merchant="ALGUIEN",
    )
    db.add(notice)
    db.commit()
    before = (balance_of(client, savings), balance_of(client, wallet))

    kept = merge(client, notice.id, typed).json()

    assert (kept["target_account_id"], kept["classification"]) == (None, "expense")
    assert (balance_of(client, savings), balance_of(client, wallet)) == before


def test_the_account_of_the_other_record_is_not_taken_when_it_is_the_destination(client, db):
    wallet = create_account(client, name="Wallet", type="wallet")
    top_up = models.Transaction(
        id=uuid.uuid4(), account_id=None, target_account_id=uuid.UUID(wallet["id"]), classification="own_transfer",
        type="transfer", amount=D("90000"), currency="COP", date=NOON, source="sms_uala", status="pending_review",
    )
    echo = models.Transaction(
        id=uuid.uuid4(), account_id=uuid.UUID(wallet["id"]), type="transfer", amount=D("90000"), currency="COP",
        date=NOON, source="gmail", status="pending_review",
    )
    db.add_all([top_up, echo])
    db.commit()

    response = merge(client, str(echo.id), str(top_up.id))

    assert response.status_code == 200, response.text
    assert (response.json()["account_id"], response.json()["target_account_id"]) == (None, wallet["id"])


def test_the_two_notices_of_a_transfer_between_two_accounts_of_the_same_bank_are_joined(client, db):
    origin = with_digits(client, create_account(client, name="Origin", type="bank", initial=500_000), "1234", "account")
    destination = with_digits(client, create_account(client, name="Destination", type="savings"), "5678", "account")
    sent = insert_transaction(db, origin["id"], type="transfer", amount="75000", source="gmail")
    received = insert_transaction(db, destination["id"], type="income", amount="75000", source="gmail",
                                  when=NOON + timedelta(minutes=1))

    # The same source announced both sides: each is offered the other.
    assert matches(client, sent) == [received] and matches(client, received) == [sent]
    kept = merge(client, received, sent).json()

    assert (kept["account_id"], kept["target_account_id"], kept["type"]) == (origin["id"], destination["id"], "transfer")
    assert client.post(f"{API}/transactions/{sent}/confirm").status_code == 200
    assert (balance_of(client, origin), balance_of(client, destination)) == (D("425000"), D("75000"))


def test_an_income_cannot_absorb_the_transfer_that_belongs_to_it(client, db, bank_account):
    other = create_account(client, name="Other", type="bank")
    sent = insert_transaction(db, bank_account["id"], type="transfer", amount="75000", source="gmail")
    received = insert_transaction(db, other["id"], type="income", amount="75000", source="gmail")

    response = merge(client, sent, received)

    assert response.status_code == 409 and error_code(response) == "merge_the_other_way"


def test_a_category_is_not_copied_onto_a_transfer(client, db):
    origin = create_account(client, name="Origin", type="bank")
    category = client.post(f"{API}/categories", json={"name": "Comida", "type": "expense"}).json()
    sent = insert_transaction(db, origin["id"], type="transfer", amount="12000", source="gmail")
    other = insert_transaction(db, origin["id"], type="transfer", amount="12000", source="sms_uala")
    db.get(models.Transaction, uuid.UUID(other)).category_id = uuid.UUID(category["id"])
    db.commit()

    kept = merge(client, other, sent).json()

    assert kept["category_id"] is None
