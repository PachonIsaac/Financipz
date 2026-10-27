import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from app.domain.entities import AccountType, Currency
from app.schemas.common import Input, Money, Name, Output, PartialUpdate


def normalize_key(value: str) -> str:
    """Bre-b keys are compared without distinguishing case, so they are stored in lowercase."""
    return value.lower()


AccountKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\S{1,100}$"),
    AfterValidator(normalize_key),
]


class AccountCreate(Input):
    name: Name
    type: AccountType
    currency: Currency
    initial_balance: Money = Decimal(0)
    # Person the money was lent to. Only for loan accounts.
    counterparty: Name | None = None
    key: AccountKey | None = None


class AccountUpdate(PartialUpdate):
    """The currency cannot change. Send key or counterparty as null to clear them."""

    required_when_sent = frozenset({"name", "type", "initial_balance", "archived"})

    name: Name | None = None
    type: AccountType | None = None
    initial_balance: Money | None = None
    counterparty: Name | None = None
    key: AccountKey | None = None
    archived: bool | None = None


class AccountOut(Output):
    id: uuid.UUID
    name: str
    type: AccountType
    currency: Currency
    initial_balance: Decimal
    counterparty: str | None
    key: str | None
    archived: bool
    # Initial balance plus confirmed movements, in the account's own currency. Can be negative.
    balance: Decimal


class IdentifierIn(Input):
    digits: Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")]
    type: Annotated[str, StringConstraints(pattern=r"^(account|debit|credit)$")]


class IdentifiersReplace(Input):
    identifiers: list[IdentifierIn]


class IdentifierOut(Output):
    digits: str
    type: str
