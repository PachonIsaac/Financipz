import uuid
from typing import TypeVar

from sqlalchemy.orm import Session

from app.core.errors import ApiError

Row = TypeVar("Row")


def get_or_404(db: Session, model: type[Row], row_id: uuid.UUID, message: str) -> Row:
    """A resource named in the URL: missing means 404."""
    row = db.get(model, row_id)
    if row is None:
        raise ApiError(404, "not_found", message)
    return row


def require(db: Session, model: type[Row], row_id: uuid.UUID, code: str, message: str) -> Row:
    """A resource referenced from the request body: missing means the data is invalid (422)."""
    row = db.get(model, row_id)
    if row is None:
        raise ApiError(422, code, message)
    return row
