from decimal import Decimal

import pytest

from app.domain.entities import Currency
from app.parsers.amounts import AmountParseError, parse_amount, parse_money


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("COP12.300,00", "12300.00"),
        ("COP1.234.567,89", "1234567.89"),
        ("COP999,99", "999.99"),
        ("$100,000", "100000"),
        ("$12,345.00", "12345.00"),
        ("$1,234,567.50", "1234567.50"),
        ("$13400.00", "13400.00"),
        ("$5100", "5100"),
        ("$99.999,99", "99999.99"),
        ("$1.000", "1000"),
        ("USD20,00", "20.00"),
        ("USD1.234,56", "1234.56"),
        ("50000", "50000"),
        ("  $5100  ", "5100"),
        ("$0,50", "0.50"),
    ],
)
def test_parses_known_formats(text, expected):
    assert parse_amount(text) == Decimal(expected)


def test_never_rounds_and_keeps_scale():
    assert str(parse_amount("$13400.00")) == "13400.00"
    assert str(parse_amount("$5100")) == "5100"


@pytest.mark.parametrize(
    ("text", "currency"),
    [
        ("COP12.300,00", Currency.COP),
        ("$5100", Currency.COP),
        ("5100", Currency.COP),
        ("USD20,00", Currency.USD),
        ("usd20,00", Currency.USD),
    ],
)
def test_detects_currency(text, currency):
    assert parse_money(text)[1] is currency


@pytest.mark.parametrize(
    "text",
    [
        "",
        "abc",
        "$",
        "COP",
        "$-5",
        "$1.5",
        "$1,5",
        "$100,0000",
        "$1000.000",
        "$12.34.56",
        "$1,23,456.78",
        "$12a",
        "EUR10,00",
        "$ 1 000",
        "1.",
        ",50",
    ],
)
def test_rejects_garbage(text):
    with pytest.raises(AmountParseError):
        parse_amount(text)


def test_error_is_a_value_error():
    assert issubclass(AmountParseError, ValueError)
