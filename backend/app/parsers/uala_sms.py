"""Parser for the SMS notifications sent by the Uala wallet.

The SMS carries no date, so the caller passes the time the message was received.
"""

import re
import unicodedata
from datetime import datetime
from decimal import Decimal

from app.domain.entities import Currency
from app.parsers.amounts import AmountParseError, parse_amount
from app.parsers.moments import localize
from app.parsers.models import NotificationKind, NotificationSource, ParsedNotification

# A "devolucion" received on one of these first days of the month is the
# physical card bonus. On any other day it is the daily yield.
CARD_BONUS_LAST_DAY = 5

MAX_TEXT_LENGTH = 1000
_MAX_RAW_LENGTH = 10 * MAX_TEXT_LENGTH

_AMOUNT = r"(?P<amount>\$\d(?:[\d.,]*\d)?)"
_BRAND = r"Ual[aá]"

_PAYMENT = re.compile(
    rf"^{_BRAND}\s+Pagaste\s+{_AMOUNT}\s+en\s+(?P<merchant>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_REFUND = re.compile(
    rf"^{_BRAND}\s+Devolvimos\s+{_AMOUNT}\s+a\s+tu\s+{_BRAND}\b",
    re.IGNORECASE,
)
_TOP_UP = re.compile(
    rf"\bTu\s+recarga\s+por\s+PSE\s+est[aá]\s+lista\b.{{0,200}}?"
    rf"\brecarga\s+por\s+{_AMOUNT}\s+a\s+tu\s+cuenta\s+{_BRAND}\b",
    re.IGNORECASE | re.DOTALL,
)
_COUNTRY_CODE = re.compile(r"^[A-Z]{3}$")


def parse_uala_sms(text: str, received_at: datetime) -> ParsedNotification | None:
    """Parse a Uala SMS. Returns None when the text is not a known form."""
    # The text comes from outside: only the start is read (real SMS are short).
    body = " ".join(text[:_MAX_RAW_LENGTH].split())[:MAX_TEXT_LENGTH]
    moment = localize(received_at)
    for parse in (_parse_payment, _parse_refund, _parse_top_up):
        result = parse(body, moment)
        if result is not None:
            return result
    return None


def _parse_payment(body: str, moment: datetime) -> ParsedNotification | None:
    match = _PAYMENT.match(body)
    amount = _amount_of(match)
    if match is None or amount is None:
        return None
    merchant = _clean_merchant(match["merchant"])
    if not merchant:
        return None
    return _build(NotificationKind.PURCHASE, amount, moment, merchant=merchant)


def _parse_refund(body: str, moment: datetime) -> ParsedNotification | None:
    match = _REFUND.match(body)
    amount = _amount_of(match)
    if amount is None:
        return None
    kind = NotificationKind.CARD_BONUS if moment.day <= CARD_BONUS_LAST_DAY else NotificationKind.YIELD
    return _build(kind, amount, moment)


def _parse_top_up(body: str, moment: datetime) -> ParsedNotification | None:
    amount = _amount_of(_TOP_UP.search(body))
    if amount is None:
        return None
    return _build(NotificationKind.TOP_UP, amount, moment)


def _amount_of(match: re.Match[str] | None) -> Decimal | None:
    if match is None:
        return None
    try:
        return parse_amount(match["amount"])
    except AmountParseError:
        return None


def _build(
    kind: NotificationKind, amount: Decimal, moment: datetime, merchant: str | None = None
) -> ParsedNotification:
    return ParsedNotification(
        source=NotificationSource.SMS_UALA,
        kind=kind,
        amount=amount,
        currency=Currency.COP,
        merchant=merchant,
        occurred_at=moment,
        occurred_on=moment.date(),
    )


def _clean_merchant(raw: str) -> str:
    """Drop trailing symbols (the bank emoji) and the country code token."""
    cleaned = _strip_trailing_symbols(raw)
    tokens = cleaned.split()
    if len(tokens) > 1 and _COUNTRY_CODE.match(tokens[-1]):
        tokens = tokens[:-1]
    return " ".join(tokens)


def _strip_trailing_symbols(value: str) -> str:
    end = len(value)
    while end > 0 and _is_decoration(value[end - 1]):
        end -= 1
    return value[:end]


def _is_decoration(char: str) -> bool:
    category = unicodedata.category(char)
    return category.startswith("S") or category in {"Mn", "Cf", "Zs", "Cc"}
