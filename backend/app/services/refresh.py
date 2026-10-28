"""Brings the exchange rate and the exchange balances up to date, from a button or when the service starts.

Each source runs in its own session, so one failing does not undo or block the other. Runs are
serialized inside the process, and a run that follows another too closely returns the previous result
instead of asking the external services again.
"""

import logging
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.config import Settings
from app.core.errors import ApiError
from app.db import models
from app.db.session import SessionFactory, session_factory
from app.domain.periods import local_today
from app.services import binance_sync, fx_rates, gmail_sync, integrations, remote_sync

log = logging.getLogger(__name__)

# A snapshot younger than this is not worth reading again when the service starts.
BINANCE_MAX_AGE = timedelta(hours=6)
# Mail is worth reading more often: a payment is something to confirm soon.
GMAIL_MAX_AGE = timedelta(hours=1)

_lock = threading.Lock()
_last: tuple[float, "RefreshResult"] | None = None


@dataclass(frozen=True)
class Step:
    status: str
    code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class RefreshResult:
    fx_rates: Step
    binance: Step
    gmail: Step
    ran_at: datetime
    cached: bool = False


def run_refresh(
    open_session: SessionFactory,
    encryption_key: str,
    min_interval_seconds: int,
    binance_sync_url: str = "",
    authorization: str | None = None,
    settings: Settings | None = None,
) -> RefreshResult:
    """Refresh the sources. Waits if a run is in progress, and reuses a run newer than the interval.

    With `binance_sync_url`, the exchange is read by that other deployment, on behalf of the same user.
    """
    with _lock:
        if _last is not None and time.monotonic() - _last[0] < min_interval_seconds:
            return replace(_last[1], cached=True)
        return _run(open_session, encryption_key, binance_sync_url, authorization, settings=settings)


def start_in_background(settings: Settings) -> threading.Thread:
    thread = threading.Thread(
        target=run_startup_refresh,
        args=(session_factory(settings.database_url), settings.encryption_key, bool(settings.binance_sync_url), settings),
        daemon=True,
        name="startup-refresh",
    )
    thread.start()
    return thread


def run_startup_refresh(
    open_session: SessionFactory,
    encryption_key: str,
    exchange_elsewhere: bool = False,
    settings: Settings | None = None,
) -> None:
    """Refresh once if the data is stale. Never raises, and never logs more than the outcome.

    When another deployment reads the exchange, only the rate is refreshed here: that deployment needs a
    signed-in person to ask it, and nobody is signed in while the service starts.
    """
    # If a refresh is already running (a button press), there is nothing to add.
    if not _lock.acquire(blocking=False):
        return
    try:
        with open_session() as db:
            if not is_stale(db, check_exchange=not exchange_elsewhere):
                return
        result = _run(open_session, encryption_key, skip_exchange=exchange_elsewhere, settings=settings)
        log.info(
            "startup refresh: fx_rates=%s binance=%s gmail=%s", result.fx_rates.status, result.binance.status, result.gmail.status
        )
    except Exception as error:  # the service must start whatever happens here
        log.warning("startup refresh failed: %s", type(error).__name__)
    finally:
        _lock.release()


def is_stale(db, check_exchange: bool = True) -> bool:
    """True when today's rate is missing, or a connected exchange was last read a while ago."""
    latest = db.scalar(select(func.max(models.FxRate.date)).where(models.FxRate.currency == "USD"))
    if latest is None or latest < local_today():
        return True
    if _read_long_ago(db, gmail_sync.GMAIL, GMAIL_MAX_AGE):
        return True
    return check_exchange and _read_long_ago(db, integrations.BINANCE, BINANCE_MAX_AGE)


def _read_long_ago(db, provider: str, max_age: timedelta) -> bool:
    """True for a connected integration that was never read, or not for a while."""
    row = integrations.get_row(db, provider)
    if row is None or row.encrypted_secret is None or row.status != "active":
        return False
    return row.last_synced_at is None or datetime.now(UTC) - row.last_synced_at > max_age


def _run(
    open_session: SessionFactory,
    encryption_key: str,
    binance_sync_url: str = "",
    authorization: str | None = None,
    skip_exchange: bool = False,
    settings: Settings | None = None,
) -> RefreshResult:
    global _last
    if skip_exchange:
        exchange = Step("not_connected", "exchange_read_elsewhere", "Binance se sincroniza desde otro servicio.")
    elif binance_sync_url:
        exchange = _forwarded_binance_step(binance_sync_url, authorization)
    else:
        exchange = _binance_step(open_session, encryption_key)
    result = RefreshResult(
        fx_rates=_fx_rates_step(open_session),
        binance=exchange,
        gmail=_gmail_step(open_session, settings),
        ran_at=datetime.now(UTC),
    )
    # A failed run is not remembered, so the next request tries again. Neither is one that left the
    # exchange out, because a button press right after it must still read the exchange.
    if not skip_exchange and "error" not in (result.fx_rates.status, result.binance.status, result.gmail.status):
        _last = (time.monotonic(), result)
    return result


def _fx_rates_step(open_session: SessionFactory) -> Step:
    def read() -> None:
        with open_session() as db:
            fx_rates.sync_rates(db)

    return _guarded(read)


def _binance_step(open_session: SessionFactory, encryption_key: str) -> Step:
    def read() -> Step | None:
        with open_session() as db:
            row = integrations.get_row(db, integrations.BINANCE)
            if row is None or row.encrypted_secret is None:
                code = "credentials_removed" if row is not None and row.status == "error" else "integration_not_connected"
                return Step("not_connected", code, "Binance no está conectado.")
            binance_sync.sync_binance(db, encryption_key)
        return None

    return _guarded(read)


# What the other deployment answers when there is no exchange to read; the same as when it is local.
NOT_CONNECTED_CODES = frozenset({"integration_not_connected", "credentials_removed"})


def _gmail_step(open_session: SessionFactory, settings: Settings | None) -> Step:
    def read() -> Step | None:
        if settings is None or not (settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri):
            return Step("not_connected", "gmail_not_configured", "La lectura del correo no está configurada.")
        with open_session() as db:
            row = integrations.get_row(db, gmail_sync.GMAIL)
            if row is None or row.encrypted_secret is None:
                return Step("not_connected", "integration_not_connected", "Gmail no está conectado.")
            gmail_sync.sync(db, settings)
        return None

    return _guarded(read)


def _forwarded_binance_step(url: str, authorization: str | None) -> Step:
    def read() -> Step | None:
        try:
            remote_sync.forward_binance_sync(url, authorization)
        except ApiError as error:
            if error.code in NOT_CONNECTED_CODES:
                return Step("not_connected", error.code, error.message)
            raise
        return None

    return _guarded(read)


def _guarded(action) -> Step:
    try:
        return action() or Step("ok")
    except ApiError as error:
        return Step("error", error.code, error.message)
    except Exception as error:
        # The type only: the text of an exchange error may include the signed request.
        log.warning("refresh step failed: %s", type(error).__name__)
        return Step("error", "internal_error", "Ocurrió un error inesperado. Intenta de nuevo.")
