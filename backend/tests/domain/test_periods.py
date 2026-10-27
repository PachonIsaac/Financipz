from datetime import date, datetime, timezone

import pytest

from app.domain.errors import DomainError
from app.domain.periods import add_months, local_today, month_bounds, month_start, parse_month, trailing_months


def test_month_bounds_are_half_open_and_cross_the_year():
    assert month_bounds(date(2026, 10, 1)) == (date(2026, 10, 1), date(2026, 11, 1))
    assert month_bounds(date(2026, 12, 1)) == (date(2026, 12, 1), date(2027, 1, 1))


def test_add_months_goes_both_ways():
    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert add_months(date(2026, 5, 1), 0) == date(2026, 5, 1)


def test_trailing_months_is_oldest_first_and_includes_the_last():
    assert trailing_months(date(2026, 2, 17), 6) == [
        date(2025, 9, 1), date(2025, 10, 1), date(2025, 11, 1),
        date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1),
    ]


def test_trailing_months_needs_a_positive_count():
    with pytest.raises(DomainError):
        trailing_months(date(2026, 2, 1), 0)


def test_month_start():
    assert month_start(date(2026, 10, 31)) == date(2026, 10, 1)


def test_parse_month():
    assert parse_month("2026-02") == date(2026, 2, 1)
    for bad in ("2026-13", "2026-2", "26-02", "2026/02", "abcd-ef", "2026-02-01", "", "9999-12", "0001-03", "1999-12", "2101-01"):
        with pytest.raises(DomainError):
            parse_month(bad)


def test_local_today_uses_colombian_time():
    # 02:30 UTC on the 1st is still the evening of the previous day in Colombia (UTC-5).
    assert local_today(datetime(2026, 11, 1, 2, 30, tzinfo=timezone.utc)) == date(2026, 10, 31)
    assert local_today(datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc)) == date(2026, 11, 1)


def test_parse_month_accepts_the_edges_of_the_year_range():
    assert parse_month("2000-01") == date(2000, 1, 1)
    assert parse_month("2100-12") == date(2100, 12, 1)
