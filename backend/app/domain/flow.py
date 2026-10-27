import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum, auto

from app.domain.entities import (
    Account,
    AccountType,
    Classification,
    Transaction,
    TransactionStatus,
    TransactionType,
    local_date,
)
from app.domain.errors import DomainError
from app.domain.fx import FxRates


class FlowKind(Enum):
    INCOME = auto()
    EXPENSE = auto()


@dataclass(frozen=True)
class FlowSummary:
    """Cash flow of a period, in COP. Categories use None for uncategorized movements."""

    income: Decimal
    expenses: Decimal
    income_by_category: dict[uuid.UUID | None, Decimal] = field(default_factory=dict)
    expenses_by_category: dict[uuid.UUID | None, Decimal] = field(default_factory=dict)

    @property
    def balance(self) -> Decimal:
        return self.income - self.expenses


def flow_kind(transaction: Transaction, source: Account) -> FlowKind | None:
    """How a transaction counts in the cash flow, or None when it stays out of it.

    Out of the flow: transfers (card payments, loans, own transfers and unclassified ones),
    balance adjustments, and anything on an exchange account. The exception is a transfer the
    user classified as an expense, which counts as one.
    """
    if source.type is AccountType.EXCHANGE:
        return None

    match transaction.type:
        case TransactionType.INCOME:
            return FlowKind.INCOME
        case TransactionType.EXPENSE:
            return FlowKind.EXPENSE
        case TransactionType.TRANSFER if transaction.classification is Classification.EXPENSE:
            return FlowKind.EXPENSE
        case _:
            return None


def cash_flow(
    accounts: Iterable[Account],
    transactions: Iterable[Transaction],
    start: date,
    end: date,
    fx: FxRates,
) -> FlowSummary:
    """Cash flow for the days from `start` (included) to `end` (excluded), in COP.

    Only confirmed transactions count. Foreign currency movements use the rate of their own day.
    """
    by_id = {account.id: account for account in accounts}
    income = Decimal(0)
    expenses = Decimal(0)
    income_by_category: dict[uuid.UUID | None, Decimal] = {}
    expenses_by_category: dict[uuid.UUID | None, Decimal] = {}

    for transaction in transactions:
        if transaction.status is not TransactionStatus.CONFIRMED:
            continue

        day = local_date(transaction.date)
        if not start <= day < end:
            continue

        try:
            source = by_id[transaction.account_id]
        except KeyError:
            raise DomainError(
                f"Transaction {transaction.id} refers to an unknown account {transaction.account_id}"
            ) from None

        kind = flow_kind(transaction, source)
        if kind is None:
            continue

        amount = fx.to_cop(transaction.amount, transaction.currency, day)
        category = transaction.category_id
        if kind is FlowKind.INCOME:
            income += amount
            income_by_category[category] = income_by_category.get(category, Decimal(0)) + amount
        else:
            expenses += amount
            expenses_by_category[category] = expenses_by_category.get(category, Decimal(0)) + amount

    return FlowSummary(
        income=income,
        expenses=expenses,
        income_by_category=income_by_category,
        expenses_by_category=expenses_by_category,
    )
