from datetime import date, datetime
from decimal import Decimal

import pytest

from app.domain.entities import LOCAL_TIMEZONE, Currency, TransactionType
from app.parsers.bancolombia import parse_bancolombia
from app.parsers.models import NotificationKind, NotificationSource

PREAMBLE = "Hola, esto es un aviso con tus movimientos. "
TAIL = " Si no fuiste tu, llama a la linea de ayuda 0000000000."


def at(year, month, day, hour, minute, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=LOCAL_TIMEZONE)


def parse(text):
    return parse_bancolombia(PREAMBLE + text + TAIL)


class TestPurchase:
    def test_credit_card_purchase(self):
        result = parse(
            "Bancolombia: Compraste COP12.300,00 en TIENDA EJEMPLO con tu T.Cred *1234, "
            "el 05/03/2026 a las 14:25."
        )

        assert result.source is NotificationSource.GMAIL
        assert result.kind is NotificationKind.PURCHASE
        assert result.amount == Decimal("12300.00")
        assert result.currency is Currency.COP
        assert result.merchant == "TIENDA EJEMPLO"
        assert result.last_digits == "1234"
        assert result.occurred_at == at(2026, 3, 5, 14, 25)
        assert result.occurred_on == date(2026, 3, 5)
        assert result.suggested_type is TransactionType.EXPENSE

    def test_debit_card_purchase(self):
        result = parse(
            "Bancolombia: Compraste COP15.000,00 en TIENDA EJEMPLO con tu T.Deb *4321, "
            "el 05/03/2026 a las 09:05."
        )

        assert result.kind is NotificationKind.PURCHASE
        assert result.last_digits == "4321"

    @pytest.mark.parametrize("merchant", ["TIENDA*EJEMPLO", "SITIO.EJEMPLO", "LA TIENDA DE EJEMPLO", "TIENDA 24 HORAS"])
    def test_merchant_with_symbols_and_words(self, merchant):
        result = parse(
            f"Bancolombia: Compraste COP9.990,00 en {merchant} con tu T.Cred *1234, el 05/03/2026 a las 14:25."
        )

        assert result.merchant == merchant

    def test_large_amount(self):
        result = parse(
            "Bancolombia: Compraste COP1.234.567,89 en TIENDA EJEMPLO con tu T.Cred *1234, "
            "el 05/03/2026 a las 14:25."
        )

        assert result.amount == Decimal("1234567.89")

    def test_usd_purchase_with_card_after_the_date(self):
        result = parse(
            "Bancolombia: Compraste USD20,00 en SITIO.EJEMPLO, el 05/03/2026 a las 14:25. "
            "Se cargo a T.Cred *1234. Gracias."
        )

        assert result.currency is Currency.USD
        assert result.amount == Decimal("20.00")
        assert result.merchant == "SITIO.EJEMPLO"
        assert result.last_digits == "1234"

    def test_cop_purchase_with_card_after_the_date(self):
        result = parse(
            "Bancolombia: Compraste COP45.000,00 en TIENDA EJEMPLO, el 05/03/2026 a las 14:25. "
            "Se cargo a T.Cred *1234."
        )

        assert result.currency is Currency.COP
        assert result.last_digits == "1234"

    def test_time_before_date(self):
        result = parse(
            "Bancolombia: Compraste COP45.000,00 en TIENDA EJEMPLO, el 14:25 a las 05/03/2026. "
            "Se cargo a T.Cred *1234."
        )

        assert result.occurred_at == at(2026, 3, 5, 14, 25)

    def test_without_preamble(self):
        result = parse_bancolombia(
            "Bancolombia: Compraste COP1.000,00 en TIENDA EJEMPLO con tu T.Cred *1234, el 05/03/2026 a las 14:25."
        )

        assert result.kind is NotificationKind.PURCHASE

    def test_extra_whitespace_and_line_breaks(self):
        result = parse_bancolombia(
            "Bancolombia:  Compraste   COP1.000,00 en\nTIENDA   EJEMPLO con tu T.Cred *1234,\nel 05/03/2026 a las 14:25."
        )

        assert result.merchant == "TIENDA EJEMPLO"


class TestPayment:
    def test_payment_from_a_product(self):
        result = parse(
            "Bancolombia: Pagaste $12,345.00 a COMERCIO EJEMPLO desde tu producto 1111 el 01/01/2026 10:00:00."
        )

        assert result.kind is NotificationKind.PAYMENT
        assert result.amount == Decimal("12345.00")
        assert result.merchant == "COMERCIO EJEMPLO"
        assert result.last_digits == "1111"
        assert result.occurred_at == at(2026, 1, 1, 10, 0, 0)
        assert result.suggested_type is TransactionType.EXPENSE

    def test_qr_payment(self):
        result = parse(
            "Bancolombia: PERSONA UNO EJEMPLO pagaste $15000.50 por codigo QR desde tu cuenta *1111 "
            "a la llave 3000000000 el 05/03/2026 a las 18:40."
        )

        assert result.kind is NotificationKind.PAYMENT
        assert result.amount == Decimal("15000.50")
        assert result.last_digits == "1111"
        assert result.target_text == "3000000000"
        assert result.merchant is None
        assert result.occurred_at == at(2026, 3, 5, 18, 40)


class TestTransferOut:
    def test_transfer_to_a_key(self):
        result = parse(
            "Bancolombia: Ana, transferiste $25000.00 a la llave @alias123 desde tu cuenta *1111 "
            "a MARIA EJEMPLO el 05/03/26 a las 18:40."
        )

        assert result.kind is NotificationKind.TRANSFER_OUT
        assert result.amount == Decimal("25000.00")
        assert result.target_text == "MARIA EJEMPLO"
        assert result.last_digits == "1111"
        assert result.occurred_at == at(2026, 3, 5, 18, 40)
        assert result.suggested_type is TransactionType.EXPENSE

    @pytest.mark.parametrize("key", ["3000000000", "@alias", "persona@ejemplo.test"])
    def test_key_formats(self, key):
        result = parse(
            f"Bancolombia: Ana, transferiste $9000.00 a la llave {key} desde tu cuenta *1111 "
            "a MARIA EJEMPLO el 05/03/26 a las 18:40."
        )

        assert result.target_text == "MARIA EJEMPLO"

    def test_transfer_to_an_account(self):
        result = parse(
            "Bancolombia: Transferiste $50000 desde tu cuenta *1111 a la cuenta *22222222222 "
            "el 05/03/2026 a las 08:15. ¿No fuiste tu? Llama."
        )

        assert result.kind is NotificationKind.TRANSFER_OUT
        assert result.amount == Decimal("50000")
        assert result.target_text == "22222222222"
        assert result.last_digits == "1111"

    def test_account_transfer_without_asterisks(self):
        result = parse(
            "Bancolombia: Transferiste $4000.50 desde tu cuenta 1111 a la cuenta 2222 el 05/03/2026 a las 08:15."
        )

        assert result.last_digits == "1111"
        assert result.target_text == "2222"

    def test_qr_transfer_with_year_first_date(self):
        result = parse(
            "Bancolombia: Transferiste $4000.50 por QR desde tu cuenta 1111 a la cuenta 2222, el 2026/03/05 18:40."
        )

        assert result.kind is NotificationKind.TRANSFER_OUT
        assert result.occurred_at == at(2026, 3, 5, 18, 40)


class TestTransferIn:
    def test_incoming_transfer(self):
        result = parse(
            "Bancolombia: Recibiste una transferencia por $100000 de MARIA EJEMPLO en tu cuenta **1111, "
            "el 05/03/2026 a las 11:00."
        )

        assert result.kind is NotificationKind.TRANSFER_IN
        assert result.amount == Decimal("100000")
        assert result.merchant == "MARIA EJEMPLO"
        assert result.last_digits == "1111"
        assert result.occurred_at == at(2026, 3, 5, 11, 0)
        assert result.suggested_type is TransactionType.INCOME

    def test_incoming_transfer_through_a_key(self):
        result = parse(
            "Bancolombia: Ana, recibiste una transferencia de MARIA EJEMPLO por $75000.00 en tu cuenta *1111 "
            "desde la llave @alias123 el 05/03/26 a las 11:00."
        )

        assert result.kind is NotificationKind.TRANSFER_IN
        assert result.amount == Decimal("75000.00")
        assert result.merchant == "MARIA EJEMPLO"
        assert result.last_digits == "1111"
        assert result.occurred_at == at(2026, 3, 5, 11, 0)

    def test_truncated_text_keeps_the_movement_without_a_date(self):
        result = parse_bancolombia(
            "Bancolombia: Ana, recibiste una transferencia de MARIA EJEMPLO por $75000.00 en tu cuenta *1111 "
            "desde la llave @alias123 el 05/"
        )

        assert result.kind is NotificationKind.TRANSFER_IN
        assert result.occurred_at is None
        assert result.occurred_on is None


class TestPayroll:
    def test_payroll(self):
        result = parse(
            "Bancolombia: Recibiste un pago de Nomina de EMPRESA EJEMPLO por $3500000.00 "
            "en tu cuenta de Ahorros el 30/01/2026 a las 06:00."
        )

        assert result.kind is NotificationKind.PAYROLL
        assert result.amount == Decimal("3500000.00")
        assert result.merchant == "EMPRESA EJEMPLO"
        assert result.last_digits is None
        assert result.occurred_at == at(2026, 1, 30, 6, 0)
        assert result.suggested_type is TransactionType.INCOME

    def test_payroll_with_accent(self):
        result = parse(
            "Bancolombia: Recibiste un pago de Nómina de EMPRESA EJEMPLO por $3.500.000,00 "
            "en tu cuenta de Ahorros el 30/01/2026 a las 06:00."
        )

        assert result.kind is NotificationKind.PAYROLL
        assert result.amount == Decimal("3500000.00")


class TestWithdrawal:
    def test_cash_withdrawal(self):
        result = parse(
            "Bancolombia: Retiraste $200.000,00 en CAJERO EJEMPLO 1 de tu T.Deb **1111 el 05/03/2026 a las 12:30."
        )

        assert result.kind is NotificationKind.WITHDRAWAL
        assert result.amount == Decimal("200000.00")
        assert result.merchant == "CAJERO EJEMPLO 1"
        assert result.last_digits == "1111"
        assert result.occurred_at == at(2026, 3, 5, 12, 30)
        assert result.suggested_type is TransactionType.TRANSFER


class TestScheduledBill:
    def test_scheduled_bill_payment_has_a_date_but_no_time(self):
        result = parse_bancolombia(
            "Bancolombia le informa pago Factura Programada EMPRESA GAS EJEMPLO 1234567 por $99.999,99 "
            "desde TC*1234. 05/03/2026. Consulta tu factura."
        )

        assert result.kind is NotificationKind.SCHEDULED_BILL
        assert result.amount == Decimal("99999.99")
        assert result.merchant == "EMPRESA GAS EJEMPLO"
        assert result.last_digits == "1234"
        assert result.occurred_at is None
        assert result.occurred_on == date(2026, 3, 5)
        assert result.suggested_type is TransactionType.EXPENSE


class TestIgnored:
    @pytest.mark.parametrize(
        "text",
        [
            "Bancolombia: tu compra en TIENDA EJEMPLO por $50.000,00 no fue exitosa, el cupo de tu T.Credito *1234 "
            "no se afecto. 14:25.05/03/2026.",
            "Por tu seguridad Bancolombia: Apagaste tu tarjeta de credito *1234 el 05/03/2026 14:25.",
            "Bancolombia: Inscribiste las facturas EMPRESA EJEMPLO en Factura Inscrita.",
            "Bancolombia: Inscribiste la cuenta de un tercero desde la app.",
            "Bancolombia: tu factura inscrita con la referencia 1234567 se vence el 05/03/2026 y se debitara el pago.",
            "Por tu seguridad Bancolombia: Ingresaste con tu clave a la app el 05/03/2026 a las 14:25.",
        ],
    )
    def test_non_movements_are_reported_as_ignored(self, text):
        result = parse_bancolombia(text)

        assert result is not None
        assert result.kind is NotificationKind.IGNORED
        assert result.is_movement is False
        assert result.amount is None
        assert result.suggested_type is None


class TestUnrecognized:
    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "Hola, tu pedido va en camino",
            "Bancolombia: Promocion especial para ti este mes",
            # Same wording but another sender.
            "OtroBanco: Compraste COP12.300,00 en TIENDA EJEMPLO con tu T.Cred *1234, el 05/03/2026 a las 14:25.",
            # Looks like a purchase but the amount is garbage.
            "Bancolombia: Compraste COPabc en TIENDA EJEMPLO con tu T.Cred *1234, el 05/03/2026 a las 14:25.",
            "Bancolombia: Compraste COP1.5 en TIENDA EJEMPLO con tu T.Cred *1234, el 05/03/2026 a las 14:25.",
            # Missing the closing date anchor.
            "Bancolombia: Compraste COP12.300,00 en TIENDA EJEMPLO con tu T.Cred *1234",
            # A purchase mentioned in a different tense.
            "Bancolombia: Comprarias COP12.300,00 en TIENDA EJEMPLO con tu T.Cred *1234, el 05/03/2026 a las 14:25.",
            "Bancolombia: Retiraste el efectivo de tu cuenta",
            "Bancolombia: Recibiste una promocion por $5000 de MARIA EJEMPLO",
        ],
    )
    def test_returns_none(self, text):
        assert parse_bancolombia(text) is None

    def test_invalid_calendar_date_does_not_raise(self):
        result = parse_bancolombia(
            "Bancolombia: Compraste COP1.000,00 en TIENDA EJEMPLO con tu T.Cred *1234, el 31/02/2026 a las 14:25."
        )

        assert result.kind is NotificationKind.PURCHASE
        assert result.occurred_at is None
        assert result.occurred_on is None

    def test_movement_wins_over_ignored_keywords(self):
        result = parse_bancolombia(
            "Por tu seguridad Bancolombia: Compraste COP1.000,00 en TIENDA EJEMPLO con tu T.Cred *1234, "
            "el 05/03/2026 a las 14:25."
        )

        assert result.kind is NotificationKind.PURCHASE


class TestDestinationKey:
    def test_a_transfer_to_a_key_keeps_the_key_and_the_name(self):
        result = parse(
            "Bancolombia: transferiste $50.000 a la llave @ejemplo desde tu cuenta *1234 a Persona Ejemplo "
            "el 05/03/2026 a las 10:00."
        )

        assert result.kind is NotificationKind.TRANSFER_OUT
        assert (result.target_key, result.target_text) == ("@ejemplo", "Persona Ejemplo")

    def test_a_payment_by_qr_to_a_key_keeps_the_key(self):
        result = parse(
            "Bancolombia: Hola pagaste $20.000 por código QR desde tu cuenta *1234 a la llave @ejemplo "
            "el 05/03/2026 a las 10:00."
        )

        assert result.target_key == "@ejemplo"

    def test_a_transfer_to_an_account_number_has_no_key(self):
        result = parse("Bancolombia: Transferiste $50.000 desde tu cuenta *1234 a la cuenta *5678, el 05/03/2026 a las 10:00.")

        assert result.target_key is None
