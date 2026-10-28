from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.gmail import ConnectOut, GmailSyncOut
from app.services import gmail_sync

router = APIRouter(prefix="/integrations/gmail", tags=["integrations"])


def _back_to_the_app(settings: Settings, **result: str) -> RedirectResponse:
    base = settings.app_url if settings.app_url.endswith("/") else settings.app_url + "/"
    return RedirectResponse(f"{base}more/gmail?{urlencode(result)}", status_code=303)


@router.post("/connect", response_model=ConnectOut, dependencies=[Depends(get_current_user)])
def connect(settings: Settings = Depends(get_settings)):
    """The address of the consent page. The browser cannot send the session on a redirect, so the app opens it."""
    return ConnectOut(authorization_url=gmail_sync.authorization_url(settings))


@router.get("/callback", include_in_schema=False)
def callback(
    code: str | None = Query(None, max_length=2000),
    state: str | None = Query(None, max_length=500),
    error: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Where Google sends the person back. It has no session: the signed state is what vouches for it."""
    if error:
        return _back_to_the_app(settings, error="access_denied")
    try:
        gmail_sync.complete_connection(db, settings, code, state)
    except ApiError as failure:
        return _back_to_the_app(settings, error=failure.code)
    return _back_to_the_app(settings, connected="1")


@router.post("/sync", response_model=GmailSyncOut, dependencies=[Depends(get_current_user)])
def sync(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Read the bank's new messages and store them as pending movements."""
    return gmail_sync.sync(db, settings)


@router.delete("", status_code=204, dependencies=[Depends(get_current_user)])
def disconnect(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Withdraw the permission and delete the stored token."""
    gmail_sync.disconnect(db, settings)
    return Response(status_code=204)
