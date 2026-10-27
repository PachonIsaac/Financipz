"""Idempotency hash for parsed movements.

The same payment can reach the backend more than once (a repeated sync, a
retried request). The hash identifies it so the second attempt is detected.

Formula: SHA-256 over these fields, joined with `|`:

    source | local day | amount | normalized merchant | last digits [| local time]

The local time (HH:MM:SS, Colombia) is appended only when the source carries
it, so two identical purchases on the same day stay distinct. The amount is
written in plain notation without trailing zeros, so `100` and `100.00` match.
"""

import hashlib
import re
import unicodedata
from datetime import datetime
from decimal import Decimal

from app.parsers.models import NotificationSource, ParsedNotification
from app.parsers.moments import localize

_SEPARATOR = "|"
_WHITESPACE = re.compile(r"\s+")


def normalize_merchant(text: str | None) -> str:
    """Upper-case, strip accents and symbols, and collapse whitespace.

    Punctuation that often distinguishes merchants (`*`, `.`, `&`, `-`) is kept.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    spaced = _WHITESPACE.sub(" ", without_marks)
    without_symbols = "".join(c for c in spaced if _keeps(c))
    return _WHITESPACE.sub(" ", without_symbols).strip().upper()


def dedupe_hash(
    *,
    source: NotificationSource | str,
    moment: datetime,
    has_time: bool,
    amount: Decimal,
    merchant: str | None,
    last_digits: str | None,
) -> str:
    """Hex SHA-256 identifying a movement. `moment` is converted to Colombia time."""
    local = localize(moment)
    fields = [
        str(source),
        local.date().isoformat(),
        _plain_amount(amount),
        normalize_merchant(merchant),
        (last_digits or "").strip(),
    ]
    if has_time:
        fields.append(local.time().isoformat(timespec="seconds"))
    return hashlib.sha256(_SEPARATOR.join(fields).encode("utf-8")).hexdigest()


def dedupe_hash_for(parsed: ParsedNotification) -> str | None:
    """Hash of a parsed movement, or None when it has no amount or day to hash."""
    if parsed.amount is None:
        return None
    if parsed.occurred_at is not None:
        moment, has_time = parsed.occurred_at, True
    elif parsed.occurred_on is not None:
        moment, has_time = datetime.combine(parsed.occurred_on, datetime.min.time()), False
    else:
        return None
    return dedupe_hash(
        source=parsed.source,
        moment=moment,
        has_time=has_time,
        amount=parsed.amount,
        merchant=parsed.merchant or parsed.target_text,
        last_digits=parsed.last_digits,
    )


def _keeps(char: str) -> bool:
    category = unicodedata.category(char)
    return not category.startswith("S") and category not in {"Cc", "Cf"}


def _plain_amount(amount: Decimal) -> str:
    return format(amount.normalize(), "f")
