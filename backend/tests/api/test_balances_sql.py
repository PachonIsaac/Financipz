import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db import models
from app.domain.balances import compute_balances
from app.domain.entities import LOCAL_TIMEZONE
from app.services.balances import account_balances, to_domain_account, to_domain_transaction

D = Decimal
ACCOUNT_TYPES = ["cash", "bank", "savings", "wallet", "credit_card", "loan", "exchange"]


def build_random_world(db, seed: int, movements: int = 150) -> None:
    """Accounts in two currencies and a mix of every kind of movement, in every status."""
    rng = random.Random(seed)
    accounts = [
        models.Account(
            id=uuid.uuid4(),
            name=f"Account {index}",
            type=rng.choice(ACCOUNT_TYPES),
            currency="USD" if index % 3 == 0 else "COP",
            initial_balance=D(rng.randint(-50_000, 50_000)),
            archived=False,
        )
        for index in range(7)
    ]
    db.add_all(accounts)
    db.flush()

    start = datetime(2026, 1, 1, 12, tzinfo=LOCAL_TIMEZONE)
    for index in range(movements):
        source = rng.choice(accounts)
        kind = rng.choice(["expense", "income", "transfer", "transfer", "adjustment_in", "adjustment_out"])
        amount = D(rng.randint(1, 900_000)) / 100
        row = models.Transaction(
            id=uuid.uuid4(),
            account_id=source.id,
            type=kind,
            amount=amount,
            currency=source.currency,
            date=start + timedelta(days=index),
            source="manual",
            status=rng.choices(["confirmed", "pending_review", "discarded"], weights=[7, 2, 1])[0],
            note="reason" if kind.startswith("adjustment") else None,
        )
        if kind == "transfer" and rng.random() < 0.8:
            target = rng.choice([account for account in accounts if account.id != source.id])
            row.target_account_id = target.id
            if target.currency != source.currency:
                row.target_amount = D(rng.randint(1, 900_000)) / 100
                row.fx_rate = D("4000.0000")
        db.add(row)
    db.commit()


def domain_balances(db) -> dict:
    accounts = [to_domain_account(row) for row in db.scalars(select(models.Account))]
    transactions = [to_domain_transaction(row) for row in db.scalars(select(models.Transaction))]
    return compute_balances(accounts, transactions)


def test_sql_balances_agree_with_the_domain_rules_on_random_data(db):
    for seed in (1, 2, 3):
        build_random_world(db, seed)

        assert account_balances(db) == domain_balances(db), f"seed {seed}"

        db.rollback()
        db.execute(models.Transaction.__table__.delete())
        db.execute(models.Account.__table__.delete())
        db.commit()


def test_asking_for_some_accounts_returns_exactly_those(db):
    build_random_world(db, seed=4, movements=60)
    everything = account_balances(db)
    chosen = list(everything)[:3]

    assert account_balances(db, chosen) == {account_id: everything[account_id] for account_id in chosen}


def test_an_account_without_movements_has_its_opening_balance(db):
    account = models.Account(
        id=uuid.uuid4(), name="Alone", type="cash", currency="COP", initial_balance=D("123.45"), archived=False
    )
    db.add(account)
    db.commit()

    assert account_balances(db, [account.id]) == {account.id: D("123.45")}
