import uuid
from collections.abc import Collection
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import models
from app.domain import entities as domain
from app.domain.balances import compute_balances


def to_domain_account(row: models.Account) -> domain.Account:
    return domain.Account(
        id=row.id,
        type=domain.AccountType(row.type),
        currency=domain.Currency(row.currency),
        initial_balance=row.initial_balance,
        archived=row.archived,
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


def account_balances(db: Session, only: Collection[uuid.UUID] | None = None) -> dict[uuid.UUID, Decimal]:
    """Balance of every account (or only the given ones), in each account's own currency."""
    accounts = [to_domain_account(row) for row in db.scalars(select(models.Account))]

    query = select(models.Transaction).where(models.Transaction.status == domain.TransactionStatus.CONFIRMED)
    if only is not None:
        query = query.where(
            or_(models.Transaction.account_id.in_(only), models.Transaction.target_account_id.in_(only))
        )
    transactions = [to_domain_transaction(row) for row in db.scalars(query)]

    balances = compute_balances(accounts, transactions)
    if only is None:
        return balances
    return {account_id: balances[account_id] for account_id in only}
