from datetime import date
from decimal import Decimal

from app.domain.envelopes import effective_reserved, months_left, next_year, suggested_monthly

D = Decimal


def test_months_count_calendar_months_to_the_payment_month():
    assert months_left(date(2026, 11, 7), date(2027, 2, 6)) == 3
    assert months_left(date(2026, 11, 30), date(2026, 12, 1)) == 1


def test_a_payment_this_month_or_overdue_counts_as_one_month():
    assert months_left(date(2026, 11, 7), date(2026, 11, 20)) == 1
    assert months_left(date(2026, 11, 7), date(2026, 1, 1)) == 1


def test_suggestion_divides_what_is_missing_and_rounds_up():
    assert suggested_monthly(D(480000), D(300000), date(2027, 2, 6), date(2026, 11, 7)) == D(60000)
    assert suggested_monthly(D(100), D(0), date(2027, 2, 6), date(2026, 11, 7)) == D(34)


def test_suggestion_is_zero_when_the_target_is_reached():
    assert suggested_monthly(D(100), D(100), date(2027, 2, 6), date(2026, 11, 7)) == D(0)
    assert suggested_monthly(D(100), D(150), date(2027, 2, 6), date(2026, 11, 7)) == D(0)


def test_no_suggestion_without_target_or_date():
    assert suggested_monthly(None, D(0), date(2027, 2, 6), date(2026, 11, 7)) is None
    assert suggested_monthly(D(100), D(0), None, date(2026, 11, 7)) is None


def test_a_year_later_survives_leap_day():
    assert next_year(date(2027, 2, 6)) == date(2028, 2, 6)
    assert next_year(date(2028, 2, 29)) == date(2029, 2, 28)


def test_reserved_never_exceeds_the_positive_balance():
    assert effective_reserved(D(500), D(800)) == D(500)
    assert effective_reserved(D(500), D(300)) == D(300)
    assert effective_reserved(D(500), D(-20)) == D(0)
    assert effective_reserved(D(-5), D(800)) == D(0)
