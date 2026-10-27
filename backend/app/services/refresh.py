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
from app.services import binance_sync, fx_rates, integrations

log = logging.getLogger(__name__)

# A snapshot younger than this is not worth reading again when the service starts.
BINANCE_MAX_AGE = timedelta(hours=6)

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
    ran_at: datetime
    cached: bool = False


def run_refresh(open_session: SessionFactory, encryption_key: str, min_interval_seconds: int) -> RefreshResult:
    """Refresh both sources. Waits if a run is in progress, and reuses a run newer than the interval."""
    with _lock:
        if _last is not None and time.monotonic() - _last[0] < min_interval_seconds:
            return replace(_last[1], cached=True)
        return _run(open_session, encryption_key)


def start_in_background(settings: Settings) -> threading.Thread:
    thread = threading.Thread(
        target=run_startup_refresh,
        args=(session_factory(settings.database_url), settings.encryption_key),
        daemon=True,
        name="startup-refresh",
    )
    thread.start()
    return thread


def run_startup_refresh(open_session: SessionFactory, encryption_key: str) -> None:
    """Refresh once if the data is stale. Never raises, and never logs more than the outcome."""
    # If a refresh is already running (a button press), there is nothing to add.
    if not _lock.acquire(blocking=False):
        return
    try:
        with open_session() as db:
            if not is_stale(db):
                return
        result = _run(open_session, encryption_key)
        log.info("startup refresh: fx_rates=%s binance=%s", result.fx_rates.status, result.binance.status)
    except Exception as error:  # the service must start whatever happens here
        log.warning("startup refresh failed: %s", type(error).__name__)
    finally:
        _lock.release()


def is_stale(db) -> bool:
    """True when today's rate is missing, or a connected exchange was last read a while ago."""
    latest = db.scalar(select(func.max(models.FxRate.date)).where(models.FxRate.currency == "USD"))
    if latest is None or latest < local_today():
        return True

    row = integrations.get_row(db, integrations.BINANCE)
    if row is None or row.encrypted_secret is None or row.status != "active":
        return False
    return row.last_synced_at is None or datetime.now(UTC) - row.last_synced_at > BINANCE_MAX_AGE


def _run(open_session: SessionFactory, encryption_key: str) -> RefreshResult:
    global _last
    result = RefreshResult(
        fx_rates=_fx_rates_step(open_session),
        binance=_binance_step(open_session, encryption_key),
        ran_at=datetime.now(UTC),
    )
    # A failed run is not remembered, so the next request tries again.
    if "error" not in (result.fx_rates.status, result.binance.status):
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


def _guarded(action) -> Step:
    try:
        return action() or Step("ok")
    except ApiError as error:
        return Step("error", error.code, error.message)
    except Exception as error:
        # The type only: the text of an exchange error may include the signed request.
        log.warning("refresh step failed: %s", type(error).__name__)
        return Step("error", "internal_error", "Ocurrió un error inesperado. Intenta de nuevo.")
