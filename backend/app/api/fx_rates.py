from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.fx_rates import FxRateOut
from app.services import fx_rates as service

router = APIRouter(prefix="/fx-rates", tags=["fx-rates"])


@router.get("", response_model=list[FxRateOut])
def list_fx_rates(
    start: date | None = Query(None, alias="from", description="First day included."),
    end: date | None = Query(None, alias="to", description="Last day included."),
    db: Session = Depends(get_db),
):
    """Stored USD rates, oldest first."""
    if start is not None and end is not None and start > end:
        raise ApiError(422, "invalid_range", "La fecha inicial no puede ser posterior a la final.")
    return service.list_rates(db, start, end)


@router.post("/sync", response_model=FxRateOut)
def sync_fx_rates(db: Session = Depends(get_db)):
    """Fetch today's rate and store it. Syncing again the same day updates the row."""
    return service.sync_current(db)
