import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator

from app.domain.entities import AccountType, Currency
from app.schemas.common import Output, to_cents

# Computed totals are answered with two decimals, like stored amounts.
Cents = Annotated[Decimal, AfterValidator(to_cents)]


class CategoryAmount(Output):
    # Null groups the movements that have no category.
    category_id: uuid.UUID | None
    name: str
    color: str | None
    amount: Cents


class MonthTotals(Output):
    month: str
    income: Cents
    expenses: Cents
    balance: Cents


class SummaryOut(Output):
    """Cash flow of a month in COP. `trend` covers the 6 months that end in `month`, oldest first."""

    month: str
    income: Cents
    expenses: Cents
    balance: Cents
    income_by_category: list[CategoryAmount]
    expenses_by_category: list[CategoryAmount]
    trend: list[MonthTotals]


class RateUsed(Output):
    currency: Currency
    value: Decimal
    date: dt.date


class WealthAccount(Output):
    id: uuid.UUID
    name: str
    type: AccountType
    currency: Currency
    archived: bool
    # In the account's own currency; can be negative.
    balance: Cents
    # Null for exchange and system accounts when no rate could value them.
    balance_cop: Cents | None


class LoanOut(Output):
    account_id: uuid.UUID
    counterparty: str | None
    amount: Cents


class CryptoOut(Output):
    """Latest crypto snapshot. All fields are null until the exchange has been synced."""

    value_usd: Cents | None = None
    # Null when there is no USD rate to convert it.
    value_cop: Cents | None = None
    snapshot_date: dt.date | None = None


class WealthOut(Output):
    """Savings view in COP, apart from the cash flow. `real_money` is negative when debt exceeds cash."""

    available: Cents
    credit_card_debt: Cents
    real_money: Cents
    receivable_loans: Cents
    loans: list[LoanOut]
    accounts: list[WealthAccount]
    crypto: CryptoOut
    # The USD rate used to value balances, or null when none is stored.
    rate: RateUsed | None
