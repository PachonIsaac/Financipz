import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.domain.errors import DomainError

# The user lives in Colombia, so calendar days and months follow this zone.
LOCAL_TIMEZONE = ZoneInfo("America/Bogota")


class AccountType(StrEnum):
    CASH = "cash"
    BANK = "bank"
    CREDIT_CARD = "credit_card"
    SAVINGS = "savings"
    WALLET = "wallet"
    EXCHANGE = "exchange"
    LOAN = "loan"
    SYSTEM = "system"


class Currency(StrEnum):
    COP = "COP"
    USD = "USD"


class TransactionType(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    ADJUSTMENT_IN = "adjustment_in"
    ADJUSTMENT_OUT = "adjustment_out"


class Classification(StrEnum):
    LOAN = "loan"
    EXPENSE = "expense"
    PAYMENT = "payment"
    OWN_TRANSFER = "own_transfer"


class TransactionStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    CONFIRMED = "confirmed"
    DISCARDED = "discarded"


@dataclass(frozen=True)
class Account:
    id: uuid.UUID
    type: AccountType
    currency: Currency
    initial_balance: Decimal = Decimal("0")
    archived: bool = False


@dataclass(frozen=True)
class Transaction:
    id: uuid.UUID
    account_id: uuid.UUID
    type: TransactionType
    amount: Decimal
    currency: Currency
    date: datetime
    status: TransactionStatus = TransactionStatus.CONFIRMED
    target_account_id: uuid.UUID | None = None
    # Amount received by the target account, in its own currency. Only for cross-currency transfers.
    target_amount: Decimal | None = None
    classification: Classification | None = None
    category_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        # Amounts are always positive. The sign comes from `type`.
        if self.amount <= 0:
            raise DomainError(f"Transaction {self.id}: amount must be positive, got {self.amount}")


def local_date(moment: datetime) -> date:
    """Calendar day of a moment in the user's timezone. Naive datetimes are taken as local."""
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(LOCAL_TIMEZONE).date()
