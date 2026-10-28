import uuid
from collections.abc import Collection
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import models
from app.domain import entities as domain
from app.domain.entities import TransactionStatus, TransactionType

# Income and positive adjustments add to the account that owns the movement. Everything else
# (expenses, negative adjustments, and the sending side of a transfer) subtracts.
_SIGNED_AMOUNT = case(
    (models.Transaction.type.in_((TransactionType.INCOME.value, TransactionType.ADJUSTMENT_IN.value)), models.Transaction.amount),
    else_=-models.Transaction.amount,
)
_CONFIRMED = models.Transaction.status == TransactionStatus.CONFIRMED.value


def account_balances(db: Session, only: Collection[uuid.UUID] | None = None) -> dict[uuid.UUID, Decimal]:
    """Balance of every account (or only the given ones), in each account's own currency.

    Computed by the database in three queries, however many movements there are. The rules are the
    same as `app.domain.balances.compute_balances`, and a test keeps both in agreement.
    """
    openings = select(models.Account.id, models.Account.initial_balance)
    sent = (
        select(models.Transaction.account_id, func.sum(_SIGNED_AMOUNT))
        .where(_CONFIRMED)
        .group_by(models.Transaction.account_id)
    )
    # The receiving side of a transfer gets the converted amount when the currencies differ.
    received = (
        select(
            models.Transaction.target_account_id,
            func.sum(func.coalesce(models.Transaction.target_amount, models.Transaction.amount)),
        )
        .where(
            _CONFIRMED,
            models.Transaction.type == TransactionType.TRANSFER.value,
            models.Transaction.target_account_id.is_not(None),
        )
        .group_by(models.Transaction.target_account_id)
    )
    if only is not None:
        openings = openings.where(models.Account.id.in_(only))
        sent = sent.where(models.Transaction.account_id.in_(only))
        received = received.where(models.Transaction.target_account_id.in_(only))

    balances = {account_id: opening for account_id, opening in db.execute(openings)}
    for account_id, total in db.execute(sent):
        if account_id in balances:
            balances[account_id] += total
    for account_id, total in db.execute(received):
        if account_id in balances:
            balances[account_id] += total
    return balances


def to_domain_account(row: models.Account) -> domain.Account:
    return domain.Account(
        id=row.id,
        type=domain.AccountType(row.type),
        currency=domain.Currency(row.currency),
        initial_balance=row.initial_balance,
        archived=row.archived,
        include_in_balance=row.include_in_balance,
    )


def to_domain_transaction(row: models.Transaction) -> domain.Transaction:
    return domain.Transaction(
        id=row.id,
        account_id=row.account_id,
        type=domain.TransactionType(row.type),
        amount=row.amount,
        currency=domain.Currency(row.currency),
        date=row.date,
        status=domain.TransactionStatus(row.status),
        target_account_id=row.target_account_id,
        target_amount=row.target_amount,
        classification=domain.Classification(row.classification) if row.classification else None,
        category_id=row.category_id,
    )
