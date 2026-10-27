"""Date and time extraction from notification text fragments."""

import re
from datetime import date, datetime, time

from app.domain.entities import LOCAL_TIMEZONE

_DATE = re.compile(r"(?P<a>\d{1,4})/(?P<b>\d{1,2})/(?P<c>\d{1,4})")
_TIME = re.compile(
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?(?:\s?(?P<meridiem>[ap])\.?\s?m\b\.?)?",
    re.IGNORECASE,
)

# How far past the cue word a date and time are searched for.
_WINDOW = 45


def find_moment(fragment: str) -> tuple[date | None, datetime | None]:
    """Find a date and an optional time at the start of `fragment`.

    Dates may be `dd/mm/yyyy`, `dd/mm/yy` or `yyyy/mm/dd`. The time may come
    before or after the date. Returns the calendar day and, when a time of day
    is present, the Colombia-aware datetime. Invalid values yield `(None, None)`.
    """
    window = fragment[:_WINDOW]
    day = _find_date(window)
    if day is None:
        return None, None
    clock = _find_time(window)
    if clock is None:
        return day, None
    return day, datetime.combine(day, clock, tzinfo=LOCAL_TIMEZONE)


def localize(moment: datetime) -> datetime:
    """Express a moment in Colombia time. Naive values are taken as local."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=LOCAL_TIMEZONE)
    return moment.astimezone(LOCAL_TIMEZONE)


def _find_date(window: str) -> date | None:
    match = _DATE.search(window)
    if match is None:
        return None
    first, month, last = match["a"], int(match["b"]), match["c"]
    if len(first) == 4:
        year_first = True
    elif len(last) in (2, 4):
        year_first = False
    else:
        return None
    try:
        if year_first:
            return date(int(first), month, int(last))
        year = int(last) + 2000 if len(last) == 2 else int(last)
        return date(year, month, int(first))
    except ValueError:
        return None


def _find_time(window: str) -> time | None:
    match = _TIME.search(window)
    if match is None:
        return None
    hour = int(match["hour"])
    meridiem = (match["meridiem"] or "").lower()
    if meridiem:
        # 12-hour clock: 12 a. m. is midnight, 12 p. m. is noon, and 1 to 12 are the only valid hours.
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "p" else 0)
    try:
        return time(hour, int(match["minute"]), int(match["second"] or 0))
    except ValueError:
        return None
