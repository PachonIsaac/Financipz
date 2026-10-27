import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, Field, field_validator

from app.domain.entities import (
    LOCAL_TIMEZONE,
    Classification,
    Currency,
    TransactionStatus,
    TransactionType,
)
from app.schemas.common import Input, Money, Output, PartialUpdate, PositiveMoney, Text
from app.schemas.enums import TransactionSource

# Movements entered by hand. Balance adjustments have their own endpoint.
ManualType = Annotated[
    TransactionType,
    Field(description="expense, income or transfer"),
]


def as_local_aware(value: datetime | None) -> datetime | None:
    """A date without a timezone is taken as Colombian time."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TIMEZONE)
    return value


class TransactionCreate(Input):
    account_id: uuid.UUID
    type: ManualType
    amount: PositiveMoney
    date: datetime | None = None
    category_id: uuid.UUID | None = None
    merchant: Text | None = None
    note: Text | None = None
    # Transfers only.
    target_account_id: uuid.UUID | None = None
    # Amount the target account receives. Only for transfers between currencies; if omitted, the
    # rate of the day is used.
    target_amount: PositiveMoney | None = None
    classification: Classification | None = None

    _local_date = field_validator("date")(as_local_aware)

    @field_validator("type")
    @classmethod
    def only_manual_types(cls, value: TransactionType) -> TransactionType:
        if value not in (TransactionType.EXPENSE, TransactionType.INCOME, TransactionType.TRANSFER):
            raise ValueError("use the adjustments endpoint for balance adjustments")
        return value


class TransactionUpdate(PartialUpdate):
    """The type, currency and status cannot change here. Use confirm and discard for the status."""

    required_when_sent = frozenset({"account_id", "amount", "date"})

    account_id: uuid.UUID | None = None
    amount: PositiveMoney | None = None
    date: datetime | None = None
    category_id: uuid.UUID | None = None
    merchant: Text | None = None
    note: Text | None = None
    target_account_id: uuid.UUID | None = None
    target_amount: PositiveMoney | None = None
    classification: Classification | None = None

    _local_date = field_validator("date")(as_local_aware)


class TransactionOut(Output):
    id: uuid.UUID
    account_id: uuid.UUID
    target_account_id: uuid.UUID | None
    target_text: str | None
    classification: Classification | None
    category_id: uuid.UUID | None
    type: TransactionType
    amount: Decimal
    currency: Currency
    # Only on transfers between currencies: what the target account received, and the rate used.
    target_amount: Decimal | None
    fx_rate: Decimal | None
    date: AwareDatetime
    merchant: str | None
    note: str | None
    source: TransactionSource
    source_id: str | None
    status: TransactionStatus
    external_reference: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class TransactionPage(Output):
    items: list[TransactionOut]
    # Pass it as `cursor` to get the next page. Null when there are no more.
    next_cursor: str | None


class AdjustmentCreate(Input):
    """Take the account's balance to the value you observe (for example, counting your cash)."""

    observed_balance: Money
    note: Annotated[str, Field(min_length=1, max_length=500)]
    date: datetime | None = None

    _local_date = field_validator("date")(as_local_aware)


class AdjustmentResult(Output):
    # Null when the balance already matched and nothing was recorded.
    transaction: TransactionOut | None
    balance: Decimal
