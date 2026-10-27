from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.fx_rates import FxRateOut
from app.services import fx_rates as service

router = APIRouter(prefix="/fx-rates", tags=["fx-rates"])


@router.get("", response_model=FxRateOut | list[FxRateOut])
def list_fx_rates(
    day: date | None = Query(None, alias="date", description="One rate: this day's or the closest earlier."),
    start: date | None = Query(None, alias="from", description="First day included."),
    end: date | None = Query(None, alias="to", description="Last day included."),
    db: Session = Depends(get_db),
):
    """With `date`, the rate in force that day. Otherwise the stored USD rates, oldest first."""
    if day is not None:
        if start is not None or end is not None:
            raise ApiError(422, "invalid_filters", "Usa una fecha o un rango, no ambos.")
        row = service.rate_on_or_before(db, day)
        if row is None:
            raise ApiError(404, "not_found", "No hay una TRM publicada para esa fecha ni antes.")
        return row

    if start is not None and end is not None and start > end:
        raise ApiError(422, "invalid_range", "La fecha inicial no puede ser posterior a la final.")
    return service.list_rates(db, start, end)


@router.post("/sync", response_model=FxRateOut)
def sync_fx_rates(db: Session = Depends(get_db)):
    """Fill in the rates missing since the last stored day and return the latest one."""
    return service.sync_rates(db)
