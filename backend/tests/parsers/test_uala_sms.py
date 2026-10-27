from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.entities import LOCAL_TIMEZONE, Currency, TransactionType
from app.parsers.models import NotificationKind, NotificationSource
from app.parsers.uala_sms import parse_uala_sms

MIDMONTH = datetime(2026, 3, 15, 9, 30, tzinfo=LOCAL_TIMEZONE)
FIRST_DAYS = datetime(2026, 3, 2, 9, 30, tzinfo=LOCAL_TIMEZONE)


def test_payment_at_a_merchant():
    result = parse_uala_sms("Ualá Pagaste $50000 en TIENDA EJEMPLO MEDELLIN COL 🏦", MIDMONTH)

    assert result.source is NotificationSource.SMS_UALA
    assert result.kind is NotificationKind.PURCHASE
    assert result.amount == Decimal("50000")
    assert result.currency is Currency.COP
    assert result.merchant == "TIENDA EJEMPLO MEDELLIN"
    assert result.occurred_at == MIDMONTH
    assert result.suggested_type is TransactionType.EXPENSE


def test_payment_with_decimals_and_double_spaces():
    result = parse_uala_sms("Ualá Pagaste $11800.50 en  TIENDA   X  BOGOTA  COL  🏦", MIDMONTH)

    assert result.amount == Decimal("11800.50")
    assert result.merchant == "TIENDA X BOGOTA"


def test_payment_with_thousands_separator():
    result = parse_uala_sms("Ualá Pagaste $1,250,000 en TIENDA X COL 🏦", MIDMONTH)

    assert result.amount == Decimal("1250000")


def test_refund_mid_month_is_yield():
    result = parse_uala_sms("Ualá Devolvimos $10000.00 a tu Ualá 💸", MIDMONTH)

    assert result.kind is NotificationKind.YIELD
    assert result.amount == Decimal("10000.00")
    assert result.suggested_type is TransactionType.INCOME
    assert result.occurred_on == MIDMONTH.date()


def test_refund_without_decimals():
    result = parse_uala_sms("Ualá Devolvimos $12 a tu Ualá 💸", MIDMONTH)

    assert result.amount == Decimal("12")


def test_refund_in_first_days_is_card_bonus():
    result = parse_uala_sms("Ualá Devolvimos $4500 a tu Ualá 💸", FIRST_DAYS)

    assert result.kind is NotificationKind.CARD_BONUS
    assert result.suggested_type is TransactionType.INCOME


@pytest.mark.parametrize(("day", "kind"), [(1, "card_bonus"), (5, "card_bonus"), (6, "yield"), (28, "yield")])
def test_card_bonus_window_boundaries(day, kind):
    received = datetime(2026, 3, day, 12, 0, tzinfo=LOCAL_TIMEZONE)

    assert parse_uala_sms("Ualá Devolvimos $100 a tu Ualá 💸", received).kind == kind


def test_day_is_taken_in_colombia_time():
    # 02:00 UTC on the 6th is still the 5th in Colombia.
    received = datetime(2026, 3, 6, 2, 0, tzinfo=timezone.utc)

    result = parse_uala_sms("Ualá Devolvimos $100 a tu Ualá 💸", received)

    assert result.kind is NotificationKind.CARD_BONUS
    assert result.occurred_at.utcoffset() == timedelta(hours=-5)


def test_naive_received_at_is_taken_as_local():
    result = parse_uala_sms("Ualá Devolvimos $100 a tu Ualá 💸", datetime(2026, 3, 2, 8, 0))

    assert result.kind is NotificationKind.CARD_BONUS
    assert result.occurred_at.tzinfo is not None


def test_top_up_by_bank_transfer():
    text = "¡Tu recarga por PSE está lista! 💰 Realizaste una recarga por $250000 a tu cuenta Ualá."

    result = parse_uala_sms(text, MIDMONTH)

    assert result.kind is NotificationKind.TOP_UP
    assert result.amount == Decimal("250000")
    assert result.suggested_type is TransactionType.TRANSFER


def test_top_up_with_decimals():
    text = "¡Tu recarga por PSE está lista! 💰 Realizaste una recarga por $250000.75 a tu cuenta Ualá."

    assert parse_uala_sms(text, MIDMONTH).amount == Decimal("250000.75")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Hola, este es un mensaje cualquiera",
        "Ualá Pagaste en TIENDA X COL",
        "Ualá Pagaste $abc en TIENDA X COL",
        "Ualá Pagaste $50000 en",
        "Ualá Devolvimos $100 a tu cuenta de otro banco",
        "Otro banco Pagaste $50000 en TIENDA X COL",
        "Tu recarga por PSE falló. Realizaste una recarga por $250000 a tu cuenta Ualá.",
        "Tu código de verificación es 123456",
        "Ualá Pagaste $1.5 en TIENDA X COL",
    ],
)
def test_unrecognized_text_returns_none(text):
    assert parse_uala_sms(text, MIDMONTH) is None
