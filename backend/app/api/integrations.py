from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.integrations import BinanceConnect, IntegrationOut, SyncOut
from app.services import binance_sync, integrations as service

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationOut])
def list_integrations(db: Session = Depends(get_db)):
    """Status of each integration. Never includes credentials."""
    return service.list_integrations(db)


@router.put("/binance", response_model=IntegrationOut)
def connect_binance(data: BinanceConnect, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Store a read-only key, encrypted. Keys that can do anything but read are refused."""
    row = service.connect_binance(
        db, settings.encryption_key, data.api_key.get_secret_value(), data.api_secret.get_secret_value()
    )
    return IntegrationOut.model_validate(row)


@router.delete("/binance", status_code=204)
def disconnect_binance(db: Session = Depends(get_db)):
    """Remove the stored credentials. Balances and trades already read are kept."""
    service.disconnect(db, service.BINANCE)
    return Response(status_code=204)


@router.post("/binance/sync", response_model=SyncOut)
def sync_binance(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Read balances and new spot trades from the exchange and store today's snapshot."""
    return binance_sync.sync_binance(db, settings.encryption_key)
