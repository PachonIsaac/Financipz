import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.entities import Account, AccountType
from app.domain.fx import FxRates

# Accounts whose balance is money the user can spend.
AVAILABLE_TYPES = frozenset(
    {AccountType.CASH, AccountType.BANK, AccountType.SAVINGS, AccountType.WALLET}
)


@dataclass(frozen=True)
class Wealth:
    """Savings view in COP, separate from the cash flow."""

    available: Decimal
    credit_card_debt: Decimal
    receivable_loans: Decimal
    receivable_loans_by_account: dict[uuid.UUID, Decimal] = field(default_factory=dict)

    @property
    def real_money(self) -> Decimal:
        """Available money minus credit card debt. Negative when the debt exceeds what is available."""
        return self.available - self.credit_card_debt


def compute_wealth(
    accounts: Iterable[Account],
    balances: Mapping[uuid.UUID, Decimal],
    fx: FxRates,
    on: date,
    include_archived: bool = True,
) -> Wealth:
    """Value balances in COP with the rate of the day `on`.

    - Available: cash, bank, savings and wallet accounts.
    - Credit card debt: cards with a negative balance. A card with a positive balance adds nothing.
    - Receivable loans: loan accounts, shown apart and never part of real money.
    - Exchange and system accounts are left out.

    Archived accounts still count while they hold money, so a balance cannot vanish by archiving.
    """
    available = Decimal(0)
    debt = Decimal(0)
    loans_by_account: dict[uuid.UUID, Decimal] = {}

    for account in accounts:
        if account.archived and not include_archived:
            continue

        value = fx.to_cop(balances[account.id], account.currency, on)
        if account.type in AVAILABLE_TYPES:
            available += value
        elif account.type is AccountType.CREDIT_CARD and value < 0:
            debt += -value
        elif account.type is AccountType.LOAN:
            loans_by_account[account.id] = value

    return Wealth(
        available=available,
        credit_card_debt=debt,
        receivable_loans=sum(loans_by_account.values(), Decimal(0)),
        receivable_loans_by_account=loans_by_account,
    )
