"""Parser for the notification emails sent by Bancolombia.

Each known form is a precompiled regex with named groups. Groups read by the
builder: `amount` (required), `merchant`, `target`, `digits`. The pattern
always ends right before the date, which is then located by `find_moment`.
"""

import re
from dataclasses import dataclass
from re import Pattern

from app.parsers.amounts import AmountParseError, parse_money
from app.parsers.models import NotificationKind, NotificationSource, ParsedNotification
from app.parsers.moments import find_moment

_FLAGS = re.IGNORECASE
# The text comes from outside. Real notifications are a couple of hundred characters, so only the
# start is read; together with the bounded patterns below, this keeps matching time small for any
# input, however hostile.
MAX_TEXT_LENGTH = 2000
_MAX_RAW_LENGTH = 10 * MAX_TEXT_LENGTH
_AMOUNT = r"(?P<amount>(?:COP|USD|\$)\s?\d(?:[\d.,]*\d)?)"
_NAME = r".{1,120}?"
# Anchor that closes a form: " el " directly followed by the date or time.
_ON = r"\s+el\s+(?=\d)"
_PRODUCT = r"T\.(?:Cred|Credito|Deb)\s*\*+(?P<digits>\d+)"
_PRODUCT_IN_TAIL = re.compile(r"T\.(?:Cred|Credito|Deb)\s*\*+(?P<digits>\d+)", _FLAGS)
# How far past the date the card digits may appear (USD purchases).
_TAIL_WINDOW = 120


@dataclass(frozen=True)
class _Form:
    kind: NotificationKind
    pattern: Pattern[str]
    # Purchases may state the card after the date instead of before it.
    digits_in_tail: bool = False


def _form(kind: NotificationKind, regex: str, digits_in_tail: bool = False) -> _Form:
    return _Form(kind, re.compile(regex, _FLAGS), digits_in_tail)


_MOVEMENT_FORMS = (
    _form(
        NotificationKind.PURCHASE,
        rf"Compraste\s+{_AMOUNT}\s+en\s+(?P<merchant>{_NAME})(?:\s+con\s+tu\s+{_PRODUCT})?,{_ON}",
        digits_in_tail=True,
    ),
    _form(
        NotificationKind.PAYMENT,
        rf"Pagaste\s+{_AMOUNT}\s+a\s+(?P<merchant>{_NAME})\s+desde\s+tu\s+producto\s+(?P<digits>\d+){_ON}",
    ),
    _form(
        NotificationKind.PAYMENT,
        rf"Bancolombia:\s+{_NAME}\s+pagaste\s+{_AMOUNT}\s+por\s+c[oó]digo\s+QR\s+desde\s+tu\s+cuenta\s+"
        rf"\*{{0,2}}(?P<digits>\d+)\s+a\s+la\s+llave\s+(?P<target>\S+){_ON}",
    ),
    _form(
        NotificationKind.TRANSFER_OUT,
        rf"transferiste\s+{_AMOUNT}\s+a\s+la\s+llave\s+\S+\s+desde\s+tu\s+cuenta\s+"
        rf"\*{{0,2}}(?P<digits>\d+)\s+a\s+(?P<target>{_NAME}){_ON}",
    ),
    _form(
        NotificationKind.TRANSFER_OUT,
        rf"Transferiste\s+{_AMOUNT}\s+(?:por\s+QR\s+)?desde\s+tu\s+cuenta\s+\*{{0,2}}(?P<digits>\d+)\s+"
        rf"a\s+la\s+cuenta\s+\*{{0,2}}(?P<target>\d+),?{_ON}",
    ),
    _form(
        NotificationKind.TRANSFER_IN,
        rf"Recibiste\s+una\s+transferencia\s+por\s+{_AMOUNT}\s+de\s+(?P<merchant>{_NAME})\s+en\s+tu\s+cuenta\s+"
        rf"\*{{0,2}}(?P<digits>\d+),?{_ON}",
    ),
    _form(
        NotificationKind.TRANSFER_IN,
        rf"recibiste\s+una\s+transferencia\s+de\s+(?P<merchant>{_NAME})\s+por\s+{_AMOUNT}\s+en\s+tu\s+cuenta\s+"
        rf"\*{{0,2}}(?P<digits>\d+)\b.{{0,80}}?\bel\s+(?=\d)",
    ),
    _form(
        NotificationKind.PAYROLL,
        rf"Recibiste\s+un\s+pago\s+de\s+N[oó]mina\s+de\s+(?P<merchant>{_NAME})\s+por\s+{_AMOUNT}\s+"
        rf"en\s+tu\s+cuenta\s+de\s+Ahorros{_ON}",
    ),
    _form(
        NotificationKind.WITHDRAWAL,
        rf"Retiraste\s+{_AMOUNT}\s+en\s+(?P<merchant>{_NAME})\s+de\s+tu\s+T\.Deb\s*\*+(?P<digits>\d+){_ON}",
    ),
    _form(
        NotificationKind.SCHEDULED_BILL,
        rf"Pago\s+Factura\s+Programada\s+(?P<merchant>{_NAME})\s+\d+\s+por\s+{_AMOUNT}\s+"
        rf"desde\s+TC\s*\*+(?P<digits>\d+)\.\s*(?=\d)",
    ),
)

_FAILED_OPERATION = re.compile(r"no\s+fue\s+exitosa", _FLAGS)

# Notifications that are not money movements.
_IGNORED_PATTERNS = tuple(
    re.compile(regex, _FLAGS)
    for regex in (
        r"no\s+fue\s+exitosa",
        r"\b(?:Apagaste|Prendiste|Encendiste)\s+tu\s+tarjeta",
        r"\bInscribiste\b",
        r"\bfactura\s+inscrita\b",
        r"\bPor\s+tu\s+seguridad\b",
    )
)
_BANK_NAME = re.compile(r"\bBancolombia\b", _FLAGS)


def parse_bancolombia(text: str) -> ParsedNotification | None:
    """Parse a Bancolombia notification. Returns None when the form is unknown."""
    body = " ".join(text[:_MAX_RAW_LENGTH].split())[:MAX_TEXT_LENGTH]
    if _BANK_NAME.search(body) is None:
        return None
    if _FAILED_OPERATION.search(body):
        # "...no fue exitosa" repeats the amount of an operation that did not happen: it must be
        # decided before any movement form gets a chance to read it as one.
        return ParsedNotification(source=NotificationSource.GMAIL, kind=NotificationKind.IGNORED)
    for form in _MOVEMENT_FORMS:
        match = form.pattern.search(body)
        if match is None:
            continue
        parsed = _build_movement(form, match, body)
        if parsed is not None:
            return parsed
    if any(pattern.search(body) for pattern in _IGNORED_PATTERNS):
        return ParsedNotification(source=NotificationSource.GMAIL, kind=NotificationKind.IGNORED)
    return None


def _build_movement(form: _Form, match: re.Match[str], body: str) -> ParsedNotification | None:
    try:
        amount, currency = parse_money(match["amount"].replace(" ", ""))
    except AmountParseError:
        return None
    tail = body[match.end():]
    day, moment = find_moment(tail)
    return ParsedNotification(
        source=NotificationSource.GMAIL,
        kind=form.kind,
        amount=amount,
        currency=currency,
        merchant=_group(match, "merchant"),
        target_text=_group(match, "target"),
        last_digits=_digits(form, match, tail),
        occurred_at=moment,
        occurred_on=day,
    )


def _digits(form: _Form, match: re.Match[str], tail: str) -> str | None:
    found = _group(match, "digits")
    if found is not None or not form.digits_in_tail:
        return found
    in_tail = _PRODUCT_IN_TAIL.search(tail[:_TAIL_WINDOW])
    return in_tail["digits"] if in_tail else None


def _group(match: re.Match[str], name: str) -> str | None:
    if name not in match.re.groupindex:
        return None
    return match[name]
