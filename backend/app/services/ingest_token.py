"""The token that lets the iOS shortcut send notifications, and nothing else.

It is random and long, shown once when it is created, and kept only as a hash. Rotating it replaces the
old one at once. It can only create pending movements: it opens no other route.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import models

PREFIX = "fzi_"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def rotate(db: Session) -> tuple[str, models.IngestToken]:
    """Replace the live token with a new one. The plain token is only returned here."""
    token = PREFIX + secrets.token_urlsafe(32)
    db.execute(delete(models.IngestToken))
    row = models.IngestToken(token_hash=_hash(token))
    db.add(row)
    db.commit()
    return token, row


def current(db: Session) -> models.IngestToken | None:
    return db.scalars(select(models.IngestToken).limit(1)).first()


def verify(db: Session, token: str | None) -> bool:
    """True when this is the live token. Marks it as used."""
    if not token or not token.startswith(PREFIX) or len(token) > 200:
        return False
    row = current(db)
    if row is None or not hmac.compare_digest(row.token_hash, _hash(token)):
        return False
    row.last_used_at = datetime.now(UTC)
    db.commit()
    return True
