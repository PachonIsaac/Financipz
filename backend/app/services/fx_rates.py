from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.entities import Currency
from app.domain.fx import FxRates
from app.domain.periods import local_today
from app.integrations import trm
from app.integrations.trm import PublishedRate, TrmError

CURRENT_SOURCE = "trm_api"
HISTORY_SOURCE = "trm_open_data"


def list_rates(db: Session, start: date | None, end: date | None) -> list[models.FxRate]:
    query = select(models.FxRate).order_by(models.FxRate.date, models.FxRate.currency)
    if start is not None:
        query = query.where(models.FxRate.date >= start)
    if end is not None:
        query = query.where(models.FxRate.date <= end)
    return list(db.scalars(query))


def load_rates(db: Session, up_to: date) -> FxRates:
    """Every stored rate up to a day. The table has one row per day, so it stays small."""
    rows = db.scalars(select(models.FxRate).where(models.FxRate.date <= up_to))
    by_currency: dict[Currency, dict[date, Decimal]] = {}
    for row in rows:
        by_currency.setdefault(Currency(row.currency), {})[row.date] = row.value
    return FxRates(by_currency)


def _upsert(db: Session, rates: Iterable[PublishedRate], source: str) -> None:
    values = [
        {"date": rate.day, "currency": Currency.USD.value, "value": rate.value, "source": source}
        for rate in rates
    ]
    if not values:
        return
    statement = insert(models.FxRate).values(values)
    statement = statement.on_conflict_do_update(
        index_elements=[models.FxRate.date, models.FxRate.currency],
        set_={"value": statement.excluded.value, "source": statement.excluded.source},
    )
    db.execute(statement)


def sync_current(db: Session) -> models.FxRate:
    """Store today's rate, replacing the one already stored for that day. Nothing is written on failure."""
    try:
        rate = trm.fetch_current()
    except TrmError as error:
        raise ApiError(
            502,
            "fx_source_unavailable",
            "No se pudo consultar la TRM. Intenta de nuevo más tarde.",
            {"reason": str(error)},
        ) from error

    _upsert(db, [rate], CURRENT_SOURCE)
    db.commit()
    row = db.get(models.FxRate, (rate.day, Currency.USD.value))
    assert row is not None
    return row


def backfill(db: Session, start: date) -> int:
    """Store the rates published since `start` that are not in the future. Returns how many were written."""
    try:
        published = trm.fetch_history(start)
    except TrmError as error:
        raise ApiError(
            502,
            "fx_source_unavailable",
            "No se pudo consultar el historial de la TRM. Intenta de nuevo más tarde.",
            {"reason": str(error)},
        ) from error

    today = local_today()
    rates = [rate for rate in published if rate.day <= today]
    _upsert(db, rates, HISTORY_SOURCE)
    db.commit()
    return len(rates)
