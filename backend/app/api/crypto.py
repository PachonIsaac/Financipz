from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.crypto import HistoryPoint, PortfolioOut, TradeOut, TradePage
from app.services import crypto as service
from app.services.crypto import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

router = APIRouter(prefix="/crypto", tags=["crypto"])


def check_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and start > end:
        raise ApiError(422, "invalid_range", "La fecha inicial no puede ser posterior a la final.")


@router.get("/portfolio", response_model=PortfolioOut)
def get_portfolio(db: Session = Depends(get_db)):
    """Balances per asset from the latest snapshot, in dollars and (with a stored rate) in pesos."""
    return service.portfolio(db)


@router.get("/history", response_model=list[HistoryPoint])
def get_history(
    start: date | None = Query(None, alias="from", description="First day included."),
    end: date | None = Query(None, alias="to", description="Last day included."),
    db: Session = Depends(get_db),
):
    """Daily total in dollars, oldest first. Days without a sync are absent."""
    check_range(start, end)
    return service.history(db, start, end)


@router.get("/trades", response_model=TradePage)
def list_trades(
    pair: str | None = Query(None, max_length=30, pattern=r"^[A-Za-z0-9]+$", description="For example BTCUSDT"),
    start: date | None = Query(None, alias="from", description="First day, in Colombian time"),
    end: date | None = Query(None, alias="to", description="Last day, included"),
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """Spot trades, newest first."""
    check_range(start, end)
    rows, next_cursor = service.list_trades(db, pair, start, end, cursor, limit)
    return TradePage(items=[TradeOut.model_validate(row) for row in rows], next_cursor=next_cursor)
