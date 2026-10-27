from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.reports import SummaryOut, WealthOut
from app.services import summary, wealth

router = APIRouter(tags=["reports"])


@router.get("/summary", response_model=SummaryOut)
def get_summary(
    month: str | None = Query(None, description="Month as YYYY-MM. Defaults to the current month in Colombia."),
    db: Session = Depends(get_db),
):
    """Cash flow of a month in COP, with spending by category and the trend of the last 6 months."""
    return summary.monthly_summary(db, summary.resolve_month(month))


@router.get("/wealth", response_model=WealthOut)
def get_wealth(db: Session = Depends(get_db)):
    """Available money, credit card debt, real money, loans owed and balances per account, in COP."""
    return wealth.current_wealth(db)
