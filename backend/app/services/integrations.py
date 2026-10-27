"""Connecting, listing and disconnecting integrations. Credentials are only ever stored encrypted."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json, encrypt_json
from app.core.errors import ApiError
from app.db import models
from app.domain.exchange_permissions import evaluate_key_restrictions
from app.integrations import binance
from app.integrations.binance import BinanceClient, BinanceError, Credentials

BINANCE = "binance"
PROVIDERS = ("gmail", "binance")


@dataclass(frozen=True)
class Notice:
    code: str
    message: str

    def as_json(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


IP_NOT_RESTRICTED = Notice(
    "ip_not_restricted",
    "La clave no está restringida por IP. Se recomienda limitarla a la dirección IP desde la que se usa.",
)
KEY_NOT_READ_ONLY = Notice(
    "key_not_read_only",
    "La clave tiene permisos distintos a lectura y se eliminó del servidor. Crea una clave nueva de solo lectura y conéctala de nuevo.",
)

# Failures of the exchange, as the API reports them. The message never includes anything from the request.
BINANCE_ERRORS: dict[str, tuple[int, str, str]] = {
    binance.INVALID_CREDENTIALS: (
        422,
        "binance_invalid_credentials",
        "Binance rechazó la clave o el secreto. Revisa que estén completos y vuelve a intentarlo.",
    ),
    binance.ACCESS_DENIED: (
        422,
        "binance_access_denied",
        "Binance rechazó el acceso: la clave no es válida, no tiene permiso de lectura o la IP no está autorizada.",
    ),
    binance.CLOCK_SKEW: (
        502,
        "binance_clock_skew",
        "El reloj del servidor no coincide con el de Binance. Intenta de nuevo en unos minutos.",
    ),
    binance.RATE_LIMITED: (
        503,
        "binance_rate_limited",
        "Binance pidió reducir las consultas. Intenta de nuevo más tarde.",
    ),
    binance.UNAVAILABLE: (
        502,
        "binance_unavailable",
        "No se pudo consultar Binance. Intenta de nuevo más tarde.",
    ),
    binance.BAD_RESPONSE: (
        502,
        "binance_bad_response",
        "Binance respondió algo que no se pudo interpretar. Intenta de nuevo más tarde.",
    ),
    binance.REJECTED: (
        502,
        "binance_rejected",
        "Binance rechazó la consulta. Intenta de nuevo más tarde.",
    ),
}


def binance_api_error(error: BinanceError) -> ApiError:
    status, code, message = BINANCE_ERRORS[error.kind]
    details: dict = {}
    if error.binance_code is not None:
        details["binance_code"] = error.binance_code
    headers = {"Retry-After": str(error.retry_after)} if error.kind == binance.RATE_LIMITED and error.retry_after else None
    return ApiError(status, code, message, details, headers)


class KeyRejected(ApiError):
    """The key can do more than read."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__(422, "binance_key_not_read_only", KEY_NOT_READ_ONLY.message, {"permissions": list(problems)})


def check_key(client: BinanceClient) -> list[Notice]:
    """Ask the exchange what the key may do. Refuse it unless it can only read; warn if not tied to an IP."""
    try:
        verdict = evaluate_key_restrictions(client.api_restrictions())
    except BinanceError as error:
        raise binance_api_error(error) from None
    if not verdict.accepted:
        raise KeyRejected(verdict.problems)
    return [] if verdict.ip_restricted else [IP_NOT_RESTRICTED]


def get_row(db: Session, provider: str) -> models.Integration | None:
    return db.scalars(select(models.Integration).where(models.Integration.provider == provider).limit(1)).first()


def list_integrations(db: Session) -> list[dict]:
    rows = {row.provider: row for row in db.scalars(select(models.Integration))}
    result = []
    for provider in PROVIDERS:
        row = rows.get(provider)
        if row is None:
            result.append({"provider": provider, "status": "disconnected", "last_synced_at": None, "warnings": []})
        else:
            result.append(
                {
                    "provider": provider,
                    "status": row.status,
                    "last_synced_at": row.last_synced_at,
                    "warnings": row.warnings,
                }
            )
    return result


def connect_binance(db: Session, encryption_key: str, api_key: str, api_secret: str) -> models.Integration:
    """Validate the key, then store it encrypted. Nothing is stored if the key is refused."""
    # Encrypting first fails closed (no valid encryption key) before anything goes to the network.
    blob = encrypt_json(encryption_key, {"api_key": api_key, "api_secret": api_secret})

    with binance.build_client(Credentials(api_key, api_secret)) as client:
        notices = check_key(client)

    values = {
        "encrypted_secret": blob,
        "status": "active",
        "warnings": [notice.as_json() for notice in notices],
    }
    # One row per provider, even if two connections arrive at the same time.
    statement = (
        insert(models.Integration)
        .values(provider=BINANCE, **values)
        .on_conflict_do_update(index_elements=[models.Integration.provider], set_=values)
        .returning(models.Integration)
        .execution_options(populate_existing=True)
    )
    row = db.scalars(statement).one()
    db.commit()
    return row


def disconnect(db: Session, provider: str) -> None:
    """Remove the credentials. Idempotent: disconnecting something not connected does nothing."""
    row = get_row(db, provider)
    if row is None:
        return
    row.encrypted_secret = None
    row.status = "disconnected"
    row.warnings = []
    db.commit()


def stored_credentials(row: models.Integration, encryption_key: str) -> Credentials:
    if row.encrypted_secret is None:
        if row.status == "error":
            raise ApiError(
                409,
                "credentials_removed",
                "La clave se eliminó porque tenía permisos distintos a lectura. Conecta una clave nueva de solo lectura.",
            )
        raise ApiError(409, "integration_not_connected", "Binance no está conectado. Conecta una clave de solo lectura primero.")
    if row.status == "disconnected":
        raise ApiError(409, "integration_not_connected", "Binance no está conectado. Conecta una clave de solo lectura primero.")
    data = decrypt_json(encryption_key, row.encrypted_secret)
    api_key, api_secret = data.get("api_key"), data.get("api_secret")
    if not api_key or not api_secret:
        raise ApiError(
            503,
            "credentials_unreadable",
            "No se pudieron descifrar las credenciales guardadas. Vuelve a conectar la integración.",
        )
    return Credentials(api_key, api_secret)
