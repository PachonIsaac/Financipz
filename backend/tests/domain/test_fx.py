from datetime import date

import pytest

from app.domain.entities import Currency
from app.domain.errors import DomainError
from app.domain.fx import FxRates
from tests.domain.helpers import D

FX = FxRates({Currency.USD: {date(2026, 10, 9): D("4000"), date(2026, 10, 12): D("4100")}})


def test_cop_has_rate_one_without_any_data():
    assert FxRates().rate(Currency.COP, date(2026, 1, 1)) == 1
    assert FxRates().to_cop(D("123.45"), Currency.COP, date(2026, 1, 1)) == D("123.45")


def test_uses_the_rate_of_the_day_when_there_is_one():
    assert FX.rate(Currency.USD, date(2026, 10, 12)) == D("4100")


def test_falls_back_to_the_closest_earlier_day():
    # Oct 10 and 11 are a weekend: they use the Friday rate.
    assert FX.rate(Currency.USD, date(2026, 10, 11)) == D("4000")
    assert FX.rate(Currency.USD, date(2026, 12, 1)) == D("4100")


def test_rejects_a_day_before_the_first_rate():
    with pytest.raises(DomainError, match="rate"):
        FX.rate(Currency.USD, date(2026, 10, 8))


def test_rejects_a_currency_without_rates():
    with pytest.raises(DomainError, match="rate"):
        FxRates().rate(Currency.USD, date(2026, 10, 9))


def test_conversion_rounds_half_up_to_cents():
    fx = FxRates({Currency.USD: {date(2026, 10, 9): D("1")}})

    assert fx.to_cop(D("10.005"), Currency.USD, date(2026, 10, 9)) == D("10.01")
