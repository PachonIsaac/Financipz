"""Telling that two records are the same movement, and joining them.

A movement can arrive twice: typed by hand and then announced by the bank, or announced by the bank and by the
wallet (a transfer between the person's own accounts). The app only suggests: a candidate has the same amount
and currency, comes from another source and is within a day. The person decides, so a real movement that
looks like another is never lost on its own.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.entities import TransactionStatus, TransactionType
from app.services.transactions import get_transaction

WINDOW = timedelta(days=1)


def candidates(db: Session, row: models.Transaction) -> list[models.Transaction]:
    """Movements that may be the same as this one, the closest in time first."""
    if row.status != TransactionStatus.PENDING_REVIEW.value:
        return []
    found = db.scalars(
        select(models.Transaction).where(
            models.Transaction.id != row.id,
            models.Transaction.status != TransactionStatus.DISCARDED.value,
            models.Transaction.amount == row.amount,
            models.Transaction.currency == row.currency,
            models.Transaction.source != row.source,
            models.Transaction.date >= row.date - WINDOW,
            models.Transaction.date <= row.date + WINDOW,
        )
    )
    return sorted(found, key=lambda other: abs(other.date - row.date))


def merge(db: Session, absorbed_id: uuid.UUID, into_id: uuid.UUID) -> models.Transaction:
    """Say that a pending movement is the same as another one: keep the other, complete it, set this one aside."""
    absorbed = get_transaction(db, absorbed_id)
    kept = get_transaction(db, into_id)
    if absorbed.id == kept.id:
        raise ApiError(422, "same_movement", "Elige otro movimiento: no se puede unir consigo mismo.")
    if absorbed.status != TransactionStatus.PENDING_REVIEW.value:
        raise ApiError(409, "not_pending", "Solo se puede unir un movimiento pendiente de revisión.")
    if kept.status == TransactionStatus.DISCARDED.value:
        raise ApiError(409, "already_discarded", "Ese movimiento está descartado.")
    if (absorbed.amount, absorbed.currency) != (kept.amount, kept.currency):
        raise ApiError(422, "not_the_same_amount", "Los dos movimientos deben tener el mismo monto y la misma moneda.")

    _complete(kept, absorbed)
    # Set aside, not deleted: it keeps its hash, so the same notification cannot come back as a new movement.
    absorbed.status = TransactionStatus.DISCARDED.value
    db.commit()
    return kept


def _complete(kept: models.Transaction, absorbed: models.Transaction) -> None:
    """Fill in what the kept movement lacks with what the other one knows. What it has is never replaced."""
    if kept.account_id is None and absorbed.account_id is not None:
        kept.account_id = absorbed.account_id
    if kept.category_id is None and absorbed.category_id is not None and kept.type == absorbed.type:
        kept.category_id = absorbed.category_id
    if not kept.merchant and absorbed.merchant:
        kept.merchant = absorbed.merchant

    both_transfers = kept.type == absorbed.type == TransactionType.TRANSFER.value
    if both_transfers and kept.target_account_id is None and absorbed.target_account_id is not None:
        if absorbed.target_account_id != kept.account_id:
            kept.target_account_id = absorbed.target_account_id
            kept.target_text = None
            kept.classification = kept.classification or absorbed.classification
            kept.target_amount = absorbed.target_amount
            kept.fx_rate = absorbed.fx_rate
