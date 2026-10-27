"""Reading the stored crypto snapshots and trades."""

import base64
import binascii
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.crypto import summarize_values
from app.domain.entities import LOCAL_TIMEZONE, Currency
from app.domain.fx import round_money
from app.schemas.crypto import HistoryPoint, PortfolioAsset, PortfolioOut
from app.schemas.reports import CryptoOut, RateUsed
from app.services.fx_rates import rate_on_or_before

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _latest_snapshot(db: Session) -> tuple[date | None, dict[str, tuple[Decimal, Decimal | None]]]:
    """Date of the latest snapshot and, per asset, its quantity and value in dollars."""
    day = db.scalar(select(func.max(models.CryptoBalance.date)))
    if day is None:
        return None, {}
    assets: dict[str, tuple[Decimal, Decimal | None]] = {}
    for row in db.scalars(select(models.CryptoBalance).where(models.CryptoBalance.date == day)):
        quantity, value = assets.get(row.asset, (Decimal(0), Decimal(0)))
        # One unpriced holding makes the whole asset unpriced: its value is not known.
        total = None if value is None or row.value_usd is None else value + row.value_usd
        assets[row.asset] = (quantity + row.quantity, total)
    return day, assets


def _in_cop(value: Decimal | None, rate: Decimal | None) -> Decimal | None:
    return None if value is None or rate is None else round_money(value * rate)


def portfolio(db: Session) -> PortfolioOut:
    day, assets = _latest_snapshot(db)
    # The snapshot is valued with the rate of its own day (or the closest earlier one), so it does not
    # change as the exchange rate moves.
    rate = rate_on_or_before(db, day) if day else None
    rate_value = rate.value if rate else None
    totals = summarize_values(value for _, value in assets.values())

    items = [
        PortfolioAsset(asset=asset, quantity=quantity, value_usd=value, value_cop=_in_cop(value, rate_value))
        for asset, (quantity, value) in assets.items()
    ]
    # Most valuable first; unpriced assets last.
    items.sort(key=lambda item: (item.value_usd is None, -(item.value_usd or 0), item.asset))
    return PortfolioOut(
        snapshot_date=day,
        total_usd=totals.total_usd if day else None,
        total_cop=_in_cop(totals.total_usd, rate_value) if day else None,
        unpriced_assets=totals.unpriced,
        rate=RateUsed(currency=Currency.USD, value=rate.value, date=rate.date) if rate else None,
        assets=items,
    )


def wealth_block(db: Session) -> CryptoOut:
    """The `crypto` part of the wealth view, from the latest snapshot and the rate of its day."""
    day, assets = _latest_snapshot(db)
    if day is None:
        return CryptoOut()
    totals = summarize_values(value for _, value in assets.values())
    rate = rate_on_or_before(db, day)
    return CryptoOut(
        value_usd=totals.total_usd,
        value_cop=_in_cop(totals.total_usd, rate.value if rate else None),
        snapshot_date=day,
        unpriced_assets=totals.unpriced,
    )


def history(db: Session, start: date | None, end: date | None) -> list[HistoryPoint]:
    """Daily total in dollars, oldest first. A day without a sync has no point."""
    query = (
        select(models.CryptoBalance.date, func.coalesce(func.sum(models.CryptoBalance.value_usd), 0))
        .group_by(models.CryptoBalance.date)
        .order_by(models.CryptoBalance.date)
    )
    if start is not None:
        query = query.where(models.CryptoBalance.date >= start)
    if end is not None:
        query = query.where(models.CryptoBalance.date <= end)
    return [HistoryPoint(date=day, total_usd=total) for day, total in db.execute(query)]


def list_trades(
    db: Session,
    pair: str | None,
    start: date | None,
    end: date | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[models.CryptoTrade], str | None]:
    """Newest first, paginated by cursor like the movements list."""
    query = select(models.CryptoTrade)
    if pair:
        query = query.where(models.CryptoTrade.pair == pair.upper())
    if start is not None:
        query = query.where(models.CryptoTrade.executed_at >= _start_of_day(start))
    if end is not None:
        query = query.where(models.CryptoTrade.executed_at < _start_of_day(end + timedelta(days=1)))
    if cursor is not None:
        moment, row_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                models.CryptoTrade.executed_at < moment,
                and_(models.CryptoTrade.executed_at == moment, models.CryptoTrade.id < row_id),
            )
        )

    rows = list(
        db.scalars(query.order_by(models.CryptoTrade.executed_at.desc(), models.CryptoTrade.id.desc()).limit(limit + 1))
    )
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1])
    return rows, next_cursor


def _start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=LOCAL_TIMEZONE)


def _encode_cursor(row: models.CryptoTrade) -> str:
    return base64.urlsafe_b64encode(f"{row.executed_at.isoformat()}|{row.id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        moment, row_id = raw.split("|")
        when = datetime.fromisoformat(moment)
        if when.tzinfo is None:
            raise ValueError("cursor date has no timezone")
        return when, uuid.UUID(row_id)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise ApiError(422, "invalid_cursor", "El cursor de paginación no es válido.") from None
