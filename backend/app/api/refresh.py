from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.db.session import SessionFactory, get_session_factory
from app.schemas.refresh import RefreshOut
from app.services import refresh as service

router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.post("", response_model=RefreshOut)
def refresh_data(
    open_session: SessionFactory = Depends(get_session_factory), settings: Settings = Depends(get_settings)
):
    """Update the exchange rate and the exchange balances. Answers 200 even if one source fails."""
    return service.run_refresh(open_session, settings.encryption_key, settings.refresh_min_interval_seconds)
