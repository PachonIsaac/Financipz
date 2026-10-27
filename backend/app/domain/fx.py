from bisect import bisect_right
from collections.abc import Mapping
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.entities import Currency
from app.domain.errors import DomainError

CENT = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class FxRates:
    """Exchange rates to COP by day. COP is the base currency and always has rate 1."""

    def __init__(self, rates: Mapping[Currency, Mapping[date, Decimal]] | None = None) -> None:
        self._days: dict[Currency, list[date]] = {}
        self._values: dict[Currency, list[Decimal]] = {}
        for currency, by_day in (rates or {}).items():
            ordered = sorted(by_day.items())
            self._days[currency] = [day for day, _ in ordered]
            self._values[currency] = [value for _, value in ordered]

    def rate(self, currency: Currency, on: date) -> Decimal:
        """Rate of the given day, or of the closest earlier day (weekends and holidays have none)."""
        if currency is Currency.COP:
            return Decimal(1)
        days = self._days.get(currency, [])
        position = bisect_right(days, on)
        if position == 0:
            raise DomainError(f"No {currency} rate on or before {on}")
        return self._values[currency][position - 1]

    def to_cop(self, amount: Decimal, currency: Currency, on: date) -> Decimal:
        if currency is Currency.COP:
            return amount
        return round_money(amount * self.rate(currency, on))
