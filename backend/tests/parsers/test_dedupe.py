import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain.entities import LOCAL_TIMEZONE, Currency
from app.parsers.dedupe import dedupe_hash, dedupe_hash_for, normalize_merchant
from app.parsers.models import NotificationKind, NotificationSource, ParsedNotification

MOMENT = datetime(2026, 3, 5, 14, 25, 10, tzinfo=LOCAL_TIMEZONE)


def make_hash(**overrides):
    values = {
        "source": NotificationSource.GMAIL,
        "moment": MOMENT,
        "has_time": True,
        "amount": Decimal("12300.00"),
        "merchant": "Tienda Ejemplo",
        "last_digits": "1234",
    }
    values.update(overrides)
    return dedupe_hash(**values)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Tienda Ejemplo", "TIENDA EJEMPLO"),
        ("  tienda   ejemplo  ", "TIENDA EJEMPLO"),
        ("Cafetería Ñandú", "CAFETERIA NANDU"),
        ("TIENDA\tEJEMPLO\n", "TIENDA EJEMPLO"),
        ("Tienda*Ejemplo", "TIENDA*EJEMPLO"),
        ("Tienda Ejemplo 🏦", "TIENDA EJEMPLO"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_merchant(raw, expected):
    assert normalize_merchant(raw) == expected


def test_normalization_is_idempotent():
    once = normalize_merchant("  Cafetería   Ejemplo ")

    assert normalize_merchant(once) == once


def test_same_input_gives_same_hash():
    assert make_hash() == make_hash()


def test_hash_is_a_sha256_hex_digest():
    digest = make_hash()

    assert len(digest) == 64
    assert int(digest, 16) >= 0


def test_hash_follows_the_documented_formula():
    # Pins the formula: changing it would break dedupe of stored movements.
    payload = "gmail|2026-03-05|12300|TIENDA EJEMPLO|1234|14:25:10"

    assert make_hash() == hashlib.sha256(payload.encode()).hexdigest()


def test_merchant_case_accents_and_spaces_do_not_matter():
    assert make_hash(merchant="Cafetería  Ejemplo") == make_hash(merchant=" CAFETERIA EJEMPLO ")


def test_amount_scale_does_not_matter():
    assert make_hash(amount=Decimal("100")) == make_hash(amount=Decimal("100.00"))
    assert make_hash(amount=Decimal("1E+2")) == make_hash(amount=Decimal("100"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": Decimal("12300.01")},
        {"moment": datetime(2026, 3, 6, 14, 25, 10, tzinfo=LOCAL_TIMEZONE)},
        {"moment": datetime(2026, 3, 5, 14, 26, 10, tzinfo=LOCAL_TIMEZONE)},
        {"merchant": "Otra Tienda"},
        {"last_digits": "9999"},
        {"last_digits": None},
        {"source": NotificationSource.SMS_UALA},
    ],
)
def test_any_field_change_changes_the_hash(overrides):
    assert make_hash(**overrides) != make_hash()


def test_time_is_ignored_when_the_source_has_no_time():
    first = make_hash(has_time=False)
    second = make_hash(has_time=False, moment=datetime(2026, 3, 5, 23, 59, tzinfo=LOCAL_TIMEZONE))

    assert first == second
    assert first != make_hash(has_time=True)


def test_day_is_taken_in_colombia_time():
    # 03:00 UTC on the 6th is 22:00 on the 5th in Colombia.
    utc_moment = datetime(2026, 3, 6, 3, 0, tzinfo=timezone.utc)
    local_moment = datetime(2026, 3, 5, 22, 0, tzinfo=LOCAL_TIMEZONE)

    assert make_hash(moment=utc_moment, has_time=False) == make_hash(moment=local_moment, has_time=False)
    assert make_hash(moment=utc_moment) == make_hash(moment=local_moment)


def test_accepts_plain_string_source():
    assert make_hash(source="gmail") == make_hash(source=NotificationSource.GMAIL)


class TestHashForParsedNotification:
    def test_uses_time_when_present(self):
        parsed = ParsedNotification(
            source=NotificationSource.GMAIL,
            kind=NotificationKind.PURCHASE,
            amount=Decimal("12300.00"),
            currency=Currency.COP,
            merchant="Tienda Ejemplo",
            last_digits="1234",
            occurred_at=MOMENT,
            occurred_on=MOMENT.date(),
        )

        assert dedupe_hash_for(parsed) == make_hash()

    def test_date_only_notification_ignores_time(self):
        parsed = ParsedNotification(
            source=NotificationSource.GMAIL,
            kind=NotificationKind.SCHEDULED_BILL,
            amount=Decimal("12300.00"),
            merchant="Tienda Ejemplo",
            last_digits="1234",
            occurred_on=date(2026, 3, 5),
        )

        assert dedupe_hash_for(parsed) == make_hash(has_time=False)

    def test_transfer_falls_back_to_target_text(self):
        parsed = ParsedNotification(
            source=NotificationSource.GMAIL,
            kind=NotificationKind.TRANSFER_OUT,
            amount=Decimal("5000"),
            target_text="Maria Ejemplo",
            last_digits="1234",
            occurred_at=MOMENT,
        )

        assert dedupe_hash_for(parsed) == make_hash(amount=Decimal("5000"), merchant="Maria Ejemplo")

    def test_ignored_or_dateless_notifications_have_no_hash(self):
        ignored = ParsedNotification(source=NotificationSource.GMAIL, kind=NotificationKind.IGNORED)
        dateless = ParsedNotification(
            source=NotificationSource.GMAIL, kind=NotificationKind.PURCHASE, amount=Decimal("1")
        )

        assert dedupe_hash_for(ignored) is None
        assert dedupe_hash_for(dateless) is None
