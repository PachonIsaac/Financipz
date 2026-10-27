from dataclasses import dataclass
from decimal import Decimal

from app.domain.entities import TransactionType
from app.domain.errors import DomainError
from app.domain.fx import round_money


@dataclass(frozen=True)
class Adjustment:
    """A balance adjustment to record. The amount is always positive; the type gives the direction."""

    type: TransactionType
    amount: Decimal
    note: str


def plan_adjustment(computed_balance: Decimal, observed_balance: Decimal, note: str) -> Adjustment | None:
    """Movement that takes the computed balance to the observed one, or None when they already match."""
    difference = round_money(observed_balance) - round_money(computed_balance)
    if difference == 0:
        return None

    if not note.strip():
        raise DomainError("A balance adjustment needs a note")

    if difference > 0:
        return Adjustment(TransactionType.ADJUSTMENT_IN, difference, note.strip())
    return Adjustment(TransactionType.ADJUSTMENT_OUT, -difference, note.strip())
