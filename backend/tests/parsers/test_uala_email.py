from datetime import date, datetime
from decimal import Decimal

import pytest

from app.domain.entities import LOCAL_TIMEZONE, Currency
from app.parsers.models import NotificationKind, NotificationSource
from app.parsers.moments import find_moment
from app.parsers.uala_email import MAX_TEXT_LENGTH, parse_uala_email

FOOTER = " ¿No reconoces este movimiento? Escríbenos a través del chat de la app. ¡Saludos! El equipo de Ualá."


def notice(
    amount="$20.000,00", name="PERSONA EJEMPLO", key="@alias", account="***********1234",
    when="04-11-2026 08:22 hs", operation="20261104ABC123456789", cost="Gratis",
):
    parts = [
        "Transferencia enviada ¡Hola NOMBRE! Te compartimos el detalle de la transferencia realizada.",
        f"Monto {amount}",
        f"Destinatario {name}",
        f"Llave destino {key}",
        f"Cuenta origen {account}",
        f"Costo de la operación {cost}",
        f"Fecha y hora {when}",
    ]
    if operation:
        parts.append(f"Id. Op. {operation}")
    return "\n\n".join(parts) + FOOTER


def test_it_reads_every_field_of_a_transfer_the_person_sent():
    result = parse_uala_email(notice())

    assert result.source is NotificationSource.GMAIL and result.kind is NotificationKind.TRANSFER_OUT
    assert (result.amount, result.currency, result.issuer) == (Decimal("20000.00"), Currency.COP, "uala")
    assert (result.target_text, result.target_key, result.last_digits) == ("PERSONA EJEMPLO", "@alias", "1234")
    assert result.operation_id == "20261104ABC123456789"
    assert result.occurred_at == datetime(2026, 11, 4, 8, 22, tzinfo=LOCAL_TIMEZONE)
    assert result.occurred_on == date(2026, 11, 4)


def test_it_reads_a_large_amount_and_keeps_only_the_end_of_the_account_number():
    result = parse_uala_email(notice(amount="$1.250.000,50", account="*****0000123456"))

    assert result.amount == Decimal("1250000.50")
    assert result.last_digits == "3456"


def test_a_phone_number_is_not_a_key_but_the_name_is_kept():
    result = parse_uala_email(notice(key="3001234567"))

    assert result.target_key is None
    assert result.target_text == "PERSONA EJEMPLO"


def test_an_alias_is_a_key_whatever_its_case():
    assert parse_uala_email(notice(key="@Alias-1")).target_key == "@Alias-1"


def test_the_operation_id_is_optional():
    result = parse_uala_email(notice(operation=None))

    assert result is not None and result.operation_id is None


def test_dates_with_dashes_and_with_two_digit_years_are_understood():
    assert find_moment("04-11-2026 08:22 hs")[0] == date(2026, 11, 4)
    assert find_moment("4-11-26 08:22")[0] == date(2026, 11, 4)
    assert find_moment("2026-11-04 08:22")[0] == date(2026, 11, 4)
    # The same separator twice: a mixture is not a date.
    assert find_moment("04/11-2026")[0] is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Hola, esto es una promoción de Ualá con todo lo que puedes hacer",
        "Transferencia recibida Monto $20.000,00 Remitente PERSONA EJEMPLO Fecha y hora 04-11-2026 08:22 hs",
        notice().replace("Monto $20.000,00", "Monto veinte mil"),
        notice().replace("Fecha y hora 04-11-2026 08:22 hs", "Fecha y hora ayer"),
    ],
)
def test_what_is_not_a_transfer_the_person_sent_is_not_recognized(text):
    assert parse_uala_email(text) is None


def test_hostile_text_is_read_in_bounded_time_and_never_leaves_the_limit():
    nasty = "Transferencia enviada " + "Monto $1 Destinatario " * 5000 + "x" * 100_000

    assert parse_uala_email(nasty) is None
    long_name = parse_uala_email(notice(name="N" * 500))
    assert long_name is None
    assert MAX_TEXT_LENGTH == 2000
