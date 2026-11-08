from datetime import date
from decimal import ROUND_CEILING, Decimal


def months_left(today: date, due: date) -> int:
    """Whole calendar months from today to the month of the payment. A payment this month or overdue counts as one."""
    return max(1, (due.year - today.year) * 12 + due.month - today.month)


def suggested_monthly(target: Decimal | None, held: Decimal, due: date | None, today: date) -> Decimal | None:
    """What to set apart each month to reach the target by the payment month, rounded up to a whole unit.

    None when there is nothing to compute from (no target or no date); zero when the envelope already holds the target.
    """
    if target is None or due is None:
        return None
    missing = target - held
    if missing <= 0:
        return Decimal(0)
    return (missing / months_left(today, due)).to_integral_value(rounding=ROUND_CEILING)


def next_year(day: date) -> date:
    """The same day a year later; February 29 becomes February 28."""
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        return day.replace(year=day.year + 1, day=28)


def effective_reserved(held: Decimal, balance: Decimal) -> Decimal:
    """What an account really keeps apart: never more than the positive balance it has."""
    return min(max(held, Decimal(0)), max(balance, Decimal(0)))
