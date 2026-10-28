"""Asks another deployment of this API to read the exchange, with the same signed-in user.

The exchange refuses requests that come from some countries. When this process runs in one of them,
the read is delegated to a deployment elsewhere: it checks the same token and the same list of allowed
users, talks to the exchange and writes to the same database, so nothing else changes.
"""

import httpx

from app.core.errors import ApiError
from app.schemas.integrations import SyncOut

# The other deployment may be asleep (about a minute to wake) before it reads the exchange.
TIMEOUT_SECONDS = 150


def forward_binance_sync(base_url: str, authorization: str | None) -> SyncOut:
    if not authorization:
        raise ApiError(401, "missing_token", "Inicia sesión para sincronizar.")
    url = f"{base_url.rstrip('/')}/integrations/binance/sync"
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = client.post(url, headers={"Authorization": authorization})
    except httpx.HTTPError:
        raise _unavailable() from None

    if response.status_code == 200:
        try:
            return SyncOut.model_validate(response.json())
        except ValueError:
            raise _unavailable() from None

    if response.status_code in (401, 403):
        # Its configuration is wrong. Passing a 401 on would sign the person out of this app for nothing.
        raise ApiError(502, "binance_worker_rejected", "El otro servicio no aceptó la sesión. Revisa su configuración.")

    # Pass on the standard error of the other deployment, so the person reads the real reason.
    try:
        error = response.json()["error"]
        raise ApiError(response.status_code if 400 <= response.status_code < 600 else 502, str(error["code"]), str(error["message"]))
    except (ValueError, KeyError, TypeError):
        raise _unavailable() from None


def _unavailable() -> ApiError:
    return ApiError(
        502,
        "binance_worker_unavailable",
        "No se pudo sincronizar Binance desde el otro servicio. Intenta de nuevo en un momento.",
    )
