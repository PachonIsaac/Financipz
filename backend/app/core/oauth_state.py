"""A short-lived, signed value that ties the return from the consent page to the person who started it.

The callback has no session (the browser comes back from another site), so the only proof that the visit
began here is this value: it is signed with the server's secret, expires in minutes, and works once: its random nonce
is remembered when it is handed out and forgotten when it is used.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

TTL_SECONDS = 300

# Nonces handed out and not yet used, with when they expire. One process serves the app, so memory is enough:
# a restart only makes a flow in progress start over.
_issued: dict[str, int] = {}


def _sign(secret: str, body: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode().rstrip("=")


def make(secret: str, now: float | None = None) -> str:
    clock = now if now is not None else time.time()
    for nonce in [item for item, expires in _issued.items() if expires <= clock]:
        del _issued[nonce]
    payload = {"exp": int(clock + TTL_SECONDS), "n": secrets.token_urlsafe(12)}
    _issued[payload["n"]] = payload["exp"]
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{body}.{_sign(secret, body.encode())}"


def valid(secret: str, state: str | None, now: float | None = None, use: bool = False) -> bool:
    """Whether the state is signed, not expired and was issued here. With `use`, it can never be accepted again."""
    if not secret or not state or state.count(".") != 1 or len(state) > 400:
        return False
    body, signature = state.split(".")
    if not hmac.compare_digest(signature, _sign(secret, body.encode())):
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        expires = int(payload["exp"])
    except (ValueError, KeyError, TypeError):
        return False
    if (now if now is not None else time.time()) >= expires:
        return False
    nonce = payload.get("n")
    if nonce not in _issued:
        return False
    if use:
        del _issued[nonce]
    return True
