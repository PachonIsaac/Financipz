from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.database import check_database

router = APIRouter(tags=["system"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "status": "ok",
        "database": check_database(settings.database_url),
    }
