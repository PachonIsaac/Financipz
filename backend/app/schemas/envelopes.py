import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import field_validator, model_validator

from typing import Annotated

from pydantic import AfterValidator

from app.schemas.common import Input, Name, Output, PartialUpdate, PositiveMoney, Text, to_cents
from app.schemas.transactions import as_local_aware


# Computed sums are always shown with two decimals, like the stored amounts.
Cents = Annotated[Decimal, AfterValidator(to_cents)]


class EnvelopeCreate(Input):
    account_id: uuid.UUID
    name: Name
    target_amount: PositiveMoney | None = None
    due_date: date | None = None
    # Off by default: only a payment that comes back every year is renewed.
    repeats_yearly: bool = False


class EnvelopeUpdate(PartialUpdate):
    """The account cannot change: move the money by freeing it and setting it apart again."""

    required_when_sent = frozenset({"name", "repeats_yearly"})

    name: Name | None = None
    target_amount: PositiveMoney | None = None
    due_date: date | None = None
    repeats_yearly: bool | None = None


class EnvelopeOut(Output):
    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str
    currency: str
    name: str
    target_amount: Decimal | None
    due_date: date | None
    repeats_yearly: bool
    # What the envelope holds.
    balance: Cents
    # Whole months to the payment month; null without a date.
    months_left: int | None
    # What to set apart this month; null without a target or a date.
    suggested_monthly: Cents | None
    # Holds the whole target.
    ready: bool
    # The account holds less than what its envelopes set apart.
    shortfall: Cents


class EnvelopeList(Output):
    envelopes: list[EnvelopeOut]
    # Totals of the envelopes in pesos (COP accounts only).
    reserved_total: Cents
    suggested_total: Cents


class EntryCreate(Input):
    kind: Literal["contribute", "release"]
    amount: PositiveMoney
    note: Text | None = None


class EntryOut(Output):
    id: uuid.UUID
    amount: Decimal
    date: date
    note: str | None
    transaction_id: uuid.UUID | None


class NewExpense(Input):
    """The expense that records the payment. It may be charged to another account, such as a card."""

    account_id: uuid.UUID
    amount: PositiveMoney
    date: datetime | None = None
    category_id: uuid.UUID | None = None
    merchant: Text | None = None
    note: Text | None = None

    _local_date = field_validator("date")(as_local_aware)


class EnvelopePay(Input):
    """Pay with the envelope either a movement that already exists or a new expense, not both."""

    transaction_id: uuid.UUID | None = None
    expense: NewExpense | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> "EnvelopePay":
        if (self.transaction_id is None) == (self.expense is None):
            raise ValueError("send either transaction_id or expense")
        return self


class PayResult(Output):
    envelope: EnvelopeOut
    transaction_id: uuid.UUID
    freed: Cents
