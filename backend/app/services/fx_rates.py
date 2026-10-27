from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.entities import Currency
from app.domain.fx import FxRates
from app.domain.periods import local_today
from app.integrations import trm
from app.integrations.trm import PublishedRate, TrmError

# Rates from the open data portal are the official ones. The fallback never replaces them.
PORTAL_SOURCE = "trm_open_data"
FALLBACK_SOURCE = "trm_api"
# Days re-read before the last stored one, so late corrections are picked up.
OVERLAP_DAYS = 3
FIRST_SYNC_DAYS = 7
MAX_CATCH_UP_DAYS = 400
USD = Currency.USD.value


def list_rates(db: Session, start: date | None, end: date | None) -> list[models.FxRate]:
    query = select(models.FxRate).order_by(models.FxRate.date, models.FxRate.currency)
    if start is not None:
        query = query.where(models.FxRate.date >= start)
    if end is not None:
        query = query.where(models.FxRate.date <= end)
    return list(db.scalars(query))


def rate_on_or_before(db: Session, day: date) -> models.FxRate | None:
    return db.scalars(
        select(models.FxRate)
        .where(models.FxRate.currency == USD, models.FxRate.date <= day)
        .order_by(models.FxRate.date.desc())
        .limit(1)
    ).first()


def load_rates(db: Session, start: date, end: date) -> FxRates:
    """Rates for the days from `start` (included) to `end` (excluded).

    Includes the latest rate on or before `start`, which values the days that have no rate of their own.
    """
    before_start = (
        select(func.max(models.FxRate.date))
        .where(models.FxRate.currency == USD, models.FxRate.date <= start)
        .scalar_subquery()
    )
    rows = db.scalars(
        select(models.FxRate).where(
            models.FxRate.currency == USD,
            models.FxRate.date < end,
            (models.FxRate.date >= start) | (models.FxRate.date == before_start),
        )
    )
    by_day: dict[date, Decimal] = {row.date: row.value for row in rows}
    return FxRates({Currency.USD: by_day})


def _upsert(db: Session, rates: Iterable[PublishedRate], source: str) -> None:
    values = [{"date": rate.day, "currency": USD, "value": rate.value, "source": source} for rate in rates]
    if not values:
        return
    statement = insert(models.FxRate).values(values)
    statement = statement.on_conflict_do_update(
        index_elements=[models.FxRate.date, models.FxRate.currency],
        set_={"value": statement.excluded.value, "source": statement.excluded.source},
        # A fallback value never replaces an official one.
        where=(models.FxRate.source != PORTAL_SOURCE) if source != PORTAL_SOURCE else None,
    )
    db.execute(statement)


def _sync_start(db: Session, today: date) -> date:
    latest = db.scalar(select(func.max(models.FxRate.date)).where(models.FxRate.currency == USD))
    if latest is None:
        return today - timedelta(days=FIRST_SYNC_DAYS)
    return max(latest - timedelta(days=OVERLAP_DAYS), today - timedelta(days=MAX_CATCH_UP_DAYS))


def _unavailable(error: TrmError) -> ApiError:
    return ApiError(
        502,
        "fx_source_unavailable",
        "No se pudo consultar la TRM. Intenta de nuevo más tarde.",
        {"reason": str(error)},
    )


def sync_rates(db: Session, start: date | None = None) -> models.FxRate:
    """Store the rates missing since the last stored day (or since `start`) and return the latest one.

    The open data portal is used first. If it cannot be read, the current-rate service is used for today
    only, and it never replaces an official row. Nothing is written when every source fails.
    """
    today = local_today()
    first = max(start, today - timedelta(days=MAX_CATCH_UP_DAYS)) if start else _sync_start(db, today)

    try:
        _upsert(db, trm.fetch_history(first, today), PORTAL_SOURCE)
    except TrmError as portal_error:
        try:
            _upsert(db, [trm.fetch_current()], FALLBACK_SOURCE)
        except TrmError:
            raise _unavailable(portal_error) from portal_error
    db.commit()

    row = rate_on_or_before(db, today)
    if row is None:
        raise _unavailable(TrmError("No rate was published for the requested days"))
    return row
