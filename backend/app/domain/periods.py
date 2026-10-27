from datetime import date, datetime

from app.domain.entities import LOCAL_TIMEZONE
from app.domain.errors import DomainError

MIN_YEAR = 2000
MAX_YEAR = 2100


def local_today(now: datetime | None = None) -> date:
    """Today's calendar day in the user's timezone."""
    moment = now or datetime.now(LOCAL_TIMEZONE)
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(LOCAL_TIMEZONE).date()


def month_start(day: date) -> date:
    """First day of the month that contains `day`."""
    return day.replace(day=1)


def add_months(first_day: date, months: int) -> date:
    """First day of the month `months` away from the month of `first_day` (negative goes back)."""
    index = first_day.year * 12 + (first_day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def month_bounds(first_day: date) -> tuple[date, date]:
    """Days of a month as a half-open range: first day included, first day of the next month excluded."""
    return first_day, add_months(first_day, 1)


def trailing_months(last: date, count: int) -> list[date]:
    """First days of the `count` months that end with the month of `last`, oldest first."""
    if count < 1:
        raise DomainError("A window needs at least one month")
    end = month_start(last)
    return [add_months(end, -offset) for offset in range(count - 1, -1, -1)]


def parse_month(value: str) -> date:
    """First day of a month written as YYYY-MM."""
    try:
        year, month = value.split("-")
        if len(year) != 4 or len(month) != 2:
            raise ValueError
        if not MIN_YEAR <= int(year) <= MAX_YEAR:
            raise ValueError
        return date(int(year), int(month), 1)
    except ValueError:
        raise DomainError(f"Invalid month {value!r}, expected YYYY-MM") from None
