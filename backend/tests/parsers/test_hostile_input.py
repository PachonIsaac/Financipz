import time
from datetime import datetime, time as clock

import pytest

from app.domain.entities import LOCAL_TIMEZONE
from app.parsers.bancolombia import MAX_TEXT_LENGTH, parse_bancolombia
from app.parsers.models import NotificationKind
from app.parsers.moments import find_moment
from app.parsers.uala_sms import parse_uala_sms

RECEIVED = datetime(2026, 3, 15, 10, 0, tzinfo=LOCAL_TIMEZONE)
TIME_LIMIT_SECONDS = 1.0

# Text that repeats the start of a known form, which is what makes naive patterns backtrack.
HOSTILE_BANCOLOMBIA = {
    "incoming transfer repeated": "Bancolombia: recibiste una transferencia de x por $1 en tu cuenta 1 " * 4000,
    "purchase without an end": "Bancolombia: Compraste COP1 en " + "a" * 200_000,
    "purchase repeated": "Bancolombia: Compraste COP1 en x, " * 8000,
    "scheduled bill repeated": "Bancolombia: Pago Factura Programada " + "a 1 " * 40_000,
    "payment without an end": "Bancolombia: Pagaste $1 a " + "b " * 100_000,
    "transfer out repeated": "Bancolombia: Transferiste $1 a la llave @x desde tu cuenta *1 a " * 4000,
    "only spaces": "Bancolombia" + " " * 500_000,
}
HOSTILE_UALA = {
    "top up repeated": "¡Tu recarga por PSE está lista! Realizaste una recarga por $1 " * 4000,
    "payment without an end": "Ualá Pagaste $1 en " + "c " * 200_000,
    "refund repeated": "Ualá Devolvimos $1 a tu Ualá " * 8000,
}


def timed(call) -> float:
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


@pytest.mark.parametrize("name", HOSTILE_BANCOLOMBIA)
def test_bancolombia_parser_answers_quickly_to_hostile_text(name):
    text = HOSTILE_BANCOLOMBIA[name]

    assert timed(lambda: parse_bancolombia(text)) < TIME_LIMIT_SECONDS


@pytest.mark.parametrize("name", HOSTILE_UALA)
def test_uala_parser_answers_quickly_to_hostile_text(name):
    text = HOSTILE_UALA[name]

    assert timed(lambda: parse_uala_sms(text, RECEIVED)) < TIME_LIMIT_SECONDS


def test_only_the_start_of_a_very_long_text_is_read():
    real = "Bancolombia: Compraste COP12.300,00 en TIENDA EJEMPLO con tu T.Cred *1234, el 05/03/2026 a las 14:25."

    # A movement that starts the text is still recognized when a long disclaimer follows it.
    assert parse_bancolombia(real + " texto " * 50_000) is not None
    # One that only appears after the limit is not read.
    assert parse_bancolombia("x " * MAX_TEXT_LENGTH + real) is None


def test_a_failed_operation_is_never_a_movement():
    failed = (
        "Bancolombia: Transferiste $50.000 desde tu cuenta *1234 a la cuenta *4321, "
        "el 05/03/2026 14:25. La transacción no fue exitosa"
    )
    failed_purchase = (
        "Bancolombia: Compraste COP12.300,00 en TIENDA EJEMPLO con tu T.Cred *1234, "
        "el 05/03/2026 a las 14:25. La compra no fue exitosa."
    )

    for text in (failed, failed_purchase):
        parsed = parse_bancolombia(text)
        assert parsed is not None
        assert parsed.kind is NotificationKind.IGNORED
        assert not parsed.is_movement
        assert parsed.amount is None


@pytest.mark.parametrize(
    ("fragment", "expected"),
    [
        ("el 05/03/2026 a las 2:25 p. m.", clock(14, 25)),
        ("el 05/03/2026 a las 2:25 p.m.", clock(14, 25)),
        ("el 05/03/2026 a las 2:25 PM", clock(14, 25)),
        ("el 05/03/2026 a las 12:30 p. m.", clock(12, 30)),
        ("el 05/03/2026 a las 12:05 a. m.", clock(0, 5)),
        ("el 05/03/2026 a las 9:40 a. m.", clock(9, 40)),
        ("el 05/03/2026 a las 14:25", clock(14, 25)),
    ],
)
def test_twelve_hour_clock(fragment, expected):
    day, moment = find_moment(fragment)

    assert day is not None
    assert moment is not None
    assert moment.timetz().replace(tzinfo=None) == expected


@pytest.mark.parametrize("fragment", ["el 05/03/2026 a las 13:00 p. m.", "el 05/03/2026 a las 0:30 a. m."])
def test_an_impossible_twelve_hour_time_is_dropped_but_the_day_is_kept(fragment):
    day, moment = find_moment(fragment)

    assert day is not None
    assert moment is None
