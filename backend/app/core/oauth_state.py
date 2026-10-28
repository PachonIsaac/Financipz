"""A short-lived, signed value that ties the return from the consent page to the person who started it.

The callback has no session (the browser comes back from another site), so the only proof that the visit
began here is this value: it is signed with the server's secret, expires in minutes, and works once per
flow because it carries a random nonce that is never reused.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

TTL_SECONDS = 600


def _sign(secret: str, body: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode().rstrip("=")


def make(secret: str, now: float | None = None) -> str:
    payload = {"exp": int((now if now is not None else time.time()) + TTL_SECONDS), "n": secrets.token_urlsafe(12)}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{body}.{_sign(secret, body.encode())}"


def valid(secret: str, state: str | None, now: float | None = None) -> bool:
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
    return (now if now is not None else time.time()) < expires
