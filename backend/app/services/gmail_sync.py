"""Connecting the mailbox and reading the bank's notifications from it.

Only the notifications of the configured senders are read, each message once (its id is remembered), and
what is kept is what the parser found: never the text. Everything the pipeline stores waits for review.
"""

import threading
from dataclasses import dataclass
from email.utils import parseaddr
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import oauth_state
from app.core.config import Settings
from app.core.crypto import decrypt_json, encrypt_json
from app.core.errors import ApiError
from app.db import models
from app.domain.entities import LOCAL_TIMEZONE
from app.integrations import gmail
from app.integrations.gmail import GmailError
from app.parsers.bancolombia import parse_bancolombia
from app.services import ingest, integrations
from app.services.integrations import Notice

GMAIL = "gmail"
# Messages listed in one read, and fetched in one read. What does not fit is read by the next one.
MAX_LISTED = 500
MAX_FETCHED_PER_SYNC = 100
# Messages that arrived while the last read was running are caught by starting a little earlier.
OVERLAP = timedelta(days=1)

NOT_CONFIGURED = ApiError(503, "gmail_not_configured", "La lectura del correo no está configurada en el servidor.")
ACCESS_REVOKED = Notice(
    "access_revoked",
    "Google retiró el permiso de lectura del correo. Conéctalo de nuevo para seguir recibiendo los avisos.",
)


@dataclass(frozen=True)
class GmailSyncResult:
    processed: int
    created: int
    duplicates: int
    ignored: int
    unrecognized: int
    last_synced_at: datetime | None
    # True when there were more messages than one read takes: reading again continues where this stopped.
    more: bool = False


# Two reads at once would fetch the same messages. The second waits, and finds them already stored.
_sync_lock = threading.Lock()


def _configured(settings: Settings) -> None:
    if not (settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri):
        raise NOT_CONFIGURED
    if not settings.encryption_key:
        raise ApiError(503, "encryption_not_configured", "El cifrado de credenciales no está configurado en el servidor.")


def authorization_url(settings: Settings) -> str:
    """Where to send the person to allow read access. The state proves the flow began from a signed-in session."""
    _configured(settings)
    return gmail.authorization_url(
        settings.google_client_id, settings.google_redirect_uri, oauth_state.make(settings.encryption_key)
    )


def _failure(error: GmailError) -> ApiError:
    if error.kind == gmail.UNAVAILABLE:
        return ApiError(502, "gmail_unavailable", "No se pudo consultar Gmail. Intenta de nuevo más tarde.")
    if error.kind == gmail.RATE_LIMITED:
        return ApiError(503, "gmail_rate_limited", "Google pidió reducir las consultas. Intenta de nuevo más tarde.")
    if error.kind == gmail.BAD_RESPONSE:
        return ApiError(502, "gmail_bad_response", "Gmail respondió algo que no se pudo interpretar.")
    return ApiError(422, "gmail_rejected", "Google rechazó la solicitud. Intenta conectar de nuevo.")


def complete_connection(db: Session, settings: Settings, code: str | None, state: str | None) -> None:
    """Finish the consent flow: check it began here, trade the code, keep the refresh token encrypted."""
    _configured(settings)
    if not oauth_state.valid(settings.encryption_key, state, use=True):
        raise ApiError(400, "invalid_state", "La solicitud de conexión venció o no es válida. Inténtalo de nuevo.")
    if not code:
        raise ApiError(400, "access_denied", "No se concedió el permiso de lectura del correo.")
    try:
        token = gmail.exchange_code(settings.google_client_id, settings.google_client_secret, settings.google_redirect_uri, code)
    except GmailError as error:
        raise _failure(error) from None

    previous = integrations.get_row(db, GMAIL)
    if previous is not None and previous.encrypted_secret is not None:
        # Connecting again replaces the old permission: it is withdrawn so it cannot be used anymore.
        try:
            gmail.revoke(decrypt_json(settings.encryption_key, previous.encrypted_secret)["refresh_token"])
        except (ApiError, KeyError):
            pass

    values = {
        "encrypted_secret": encrypt_json(settings.encryption_key, {"refresh_token": token}),
        "status": "active",
        "warnings": [],
    }
    statement = (
        insert(models.Integration)
        .values(provider=GMAIL, **values)
        .on_conflict_do_update(index_elements=[models.Integration.provider], set_=values)
    )
    db.execute(statement)
    db.commit()


def disconnect(db: Session, settings: Settings) -> None:
    """Withdraw the permission at Google (best effort) and delete the stored token."""
    row = integrations.get_row(db, GMAIL)
    if row is not None and row.encrypted_secret is not None and settings.encryption_key:
        try:
            gmail.revoke(decrypt_json(settings.encryption_key, row.encrypted_secret)["refresh_token"])
        except (ApiError, KeyError):
            pass
    integrations.disconnect(db, GMAIL)


def _connected(db: Session) -> models.Integration:
    row = integrations.get_row(db, GMAIL)
    if row is None or row.encrypted_secret is None or row.status == "disconnected":
        code = "credentials_removed" if row is not None and row.status == "error" else "integration_not_connected"
        raise ApiError(409, code, "Gmail no está conectado. Conéctalo para leer los avisos del banco.")
    return row


def _first_read_start(settings: Settings, now: datetime) -> datetime:
    """The start of today in Colombia, minus the days asked for."""
    today = now.astimezone(LOCAL_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=settings.gmail_first_sync_days)


def _query(settings: Settings, since: datetime) -> str:
    senders = " OR ".join(settings.senders)
    return f"from:({senders}) after:{int(since.timestamp())}"


def _from_a_known_sender(settings: Settings, sender: str) -> bool:
    """The address in the From header, not the name beside it, which anyone can write."""
    address = parseaddr(sender)[1].lower()
    return address in {item.lower() for item in settings.senders}


def sync(db: Session, settings: Settings) -> GmailSyncResult:
    """Read the messages of the bank that have not been read yet and store what they say as pending movements."""
    with _sync_lock:
        return _sync(db, settings)


def _revoked(db: Session, row: models.Integration) -> ApiError:
    row.encrypted_secret = None
    row.status = "error"
    row.warnings = [ACCESS_REVOKED.as_json()]
    db.commit()
    return ApiError(409, "gmail_access_revoked", ACCESS_REVOKED.message)


def _sync(db: Session, settings: Settings) -> GmailSyncResult:
    _configured(settings)
    row = _connected(db)
    now = datetime.now(UTC)
    since = (row.last_synced_at - OVERLAP) if row.last_synced_at else _first_read_start(settings, now)

    try:
        refresh_token = decrypt_json(settings.encryption_key, row.encrypted_secret)["refresh_token"]
        access = gmail.refresh_access_token(settings.google_client_id, settings.google_client_secret, refresh_token)
    except KeyError:
        raise ApiError(503, "credentials_unreadable", "No se pudieron descifrar las credenciales guardadas. Conecta Gmail de nuevo.") from None
    except GmailError as error:
        if error.kind == gmail.REVOKED:
            raise _revoked(db, row) from None
        raise _failure(error) from None

    counts = {"created": 0, "duplicates": 0, "ignored": 0, "unrecognized": 0}
    processed = 0
    more = False
    try:
        with gmail.GmailClient(access) as client:
            ids, truncated = client.list_message_ids(_query(settings, since), MAX_LISTED)
            known = set(db.scalars(select(models.ProcessedEmail.message_id).where(models.ProcessedEmail.message_id.in_(ids))))
            # Oldest first, so the movements are stored in the order they happened, and a long backlog is
            # worked through from its start.
            unread = [item for item in reversed(ids) if item not in known]
            more = truncated or len(unread) > MAX_FETCHED_PER_SYNC
            for message_id in unread[:MAX_FETCHED_PER_SYNC]:
                message = client.get_message(message_id)
                if _from_a_known_sender(settings, message.sender):
                    outcome = ingest.ingest(db, parse_bancolombia(message.text)).outcome
                else:
                    # Gmail's search also matches the display name: a message that only claims to be the bank is not read.
                    outcome = ingest.Outcome.IGNORED
                counts[_bucket(outcome)] += 1
                db.execute(
                    insert(models.ProcessedEmail)
                    .values(
                        integration_id=row.id,
                        message_id=message_id,
                        sender=message.sender[:200] or None,
                        received_at=message.received_at,
                        result=_recorded_result(outcome),
                    )
                    .on_conflict_do_nothing(index_elements=[models.ProcessedEmail.message_id])
                )
                db.commit()
                processed += 1
    except GmailError as error:
        if error.kind == gmail.REVOKED:
            raise _revoked(db, row) from None
        raise _failure(error) from None

    # The clock only moves when everything in the window was seen: otherwise the next read starts from the
    # same point, skips what is stored, and continues.
    if not more:
        row.last_synced_at = now
        db.commit()
    return GmailSyncResult(processed=processed, last_synced_at=row.last_synced_at, more=more, **counts)


def _bucket(outcome: ingest.Outcome) -> str:
    return {
        ingest.Outcome.CREATED: "created",
        ingest.Outcome.DUPLICATE: "duplicates",
        ingest.Outcome.IGNORED: "ignored",
        ingest.Outcome.UNRECOGNIZED: "unrecognized",
    }[outcome]


def _recorded_result(outcome: ingest.Outcome) -> str:
    return {
        ingest.Outcome.CREATED: "ok",
        ingest.Outcome.DUPLICATE: "ok",
        ingest.Outcome.IGNORED: "ignored",
        ingest.Outcome.UNRECOGNIZED: "unrecognized",
    }[outcome]
