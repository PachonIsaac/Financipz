"""Money amount parsing for notification texts.

Rule: the last separator (dot or comma) followed by exactly two digits is the
decimal separator. Followed by exactly three digits it is a thousands
separator. Any other shape is rejected.
"""

import re
from decimal import Decimal

from app.domain.entities import Currency

_MONEY = re.compile(
    r"^(?P<prefix>COP|USD|US\$|\$)?\s*(?P<number>\d[\d.,]*)$",
    re.IGNORECASE,
)
_PLAIN_INTEGER = re.compile(r"^\d+$")
_GROUPED_INTEGER = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_LAST_SEPARATOR = re.compile(r"[.,](?P<tail>\d*)$")

_CURRENCY_BY_PREFIX = {
    "COP": Currency.COP,
    "$": Currency.COP,
    "USD": Currency.USD,
    "US$": Currency.USD,
}


class AmountParseError(ValueError):
    """The text is not a valid money amount."""


def parse_amount(text: str) -> Decimal:
    """Parse an amount such as `COP12.300,00`, `$100,000` or `$13400.00`."""
    return parse_money(text)[0]


def parse_money(text: str) -> tuple[Decimal, Currency]:
    """Parse an amount and its currency. Without a prefix the currency is COP."""
    match = _MONEY.match(text.strip())
    if match is None:
        raise AmountParseError(f"Not a money amount: {text!r}")
    prefix = (match["prefix"] or "$").upper()
    return _parse_number(match["number"], text), _CURRENCY_BY_PREFIX[prefix]


def _parse_number(number: str, original: str) -> Decimal:
    separator = _LAST_SEPARATOR.search(number)
    if separator is None:
        return Decimal(number)
    tail = separator["tail"]
    integer_part = number[: separator.start()]
    if len(tail) == 2:
        _require_integer(integer_part, original)
        return Decimal(f"{_digits(integer_part)}.{tail}")
    if len(tail) == 3:
        _require_integer(number, original)
        return Decimal(_digits(number))
    raise AmountParseError(f"Ambiguous separators in amount: {original!r}")


def _require_integer(candidate: str, original: str) -> None:
    if _PLAIN_INTEGER.match(candidate) or _GROUPED_INTEGER.match(candidate):
        return
    raise AmountParseError(f"Malformed digit grouping in amount: {original!r}")


def _digits(value: str) -> str:
    return re.sub(r"[.,]", "", value)
