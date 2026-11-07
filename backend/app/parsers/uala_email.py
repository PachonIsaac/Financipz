"""Parser for the notification emails sent by the Uala wallet.

Only the transfer the person sent is read ("Transferencia enviada"): it names the amount, the recipient, the key or
phone number it went to, the end of the account it left from, the moment and the id of the operation. Anything else
Uala sends gives None.
"""

import re

from app.parsers.amounts import AmountParseError, parse_money
from app.parsers.models import NotificationKind, NotificationSource, ParsedNotification
from app.parsers.moments import find_moment

ISSUER = "uala"
# The text comes from outside: only the start is read, and the patterns below are bounded.
MAX_TEXT_LENGTH = 2000
_MAX_RAW_LENGTH = 10 * MAX_TEXT_LENGTH

_TRANSFER = re.compile(
    r"Transferencia\s+enviada\b.{0,200}?"
    r"\bMonto\s+(?P<amount>(?:COP|\$)\s?\d(?:[\d.,]*\d)?)\s+"
    r"Destinatario\s+(?P<name>.{1,120}?)\s+"
    r"Llave\s+destino\s+(?P<key>\S{1,60})\s+"
    r"Cuenta\s+origen\s+[*\s]{0,20}(?P<digits>\d{1,20})\b.{0,120}?"
    r"Fecha\s+y\s+hora\s+(?P<when>\d{1,2}-\d{1,2}-\d{2,4}\s+\d{1,2}:\d{2})"
    r"(?:.{0,40}?\bId\.?\s*Op\.?\s+(?P<operation>[A-Za-z0-9]{6,60}))?",
    re.IGNORECASE,
)


def parse_uala_email(text: str) -> ParsedNotification | None:
    """Parse a Uala email. Returns None when it is not a transfer the person sent."""
    body = " ".join(text[:_MAX_RAW_LENGTH].split())[:MAX_TEXT_LENGTH]
    match = _TRANSFER.search(body)
    if match is None:
        return None
    try:
        amount, currency = parse_money(match["amount"].replace(" ", ""))
    except AmountParseError:
        return None
    day, moment = find_moment(match["when"])
    key = match["key"]
    return ParsedNotification(
        source=NotificationSource.GMAIL,
        kind=NotificationKind.TRANSFER_OUT,
        amount=amount,
        currency=currency,
        target_text=match["name"],
        # A phone number is also a valid destination, but only an alias can be matched with the person's own keys.
        target_key=key if key.startswith("@") else None,
        last_digits=match["digits"][-4:],
        occurred_at=moment,
        occurred_on=day,
        issuer=ISSUER,
        operation_id=match["operation"],
    )
