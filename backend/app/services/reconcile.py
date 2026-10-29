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
from app.domain.entities import AccountType, Classification, TransactionStatus, TransactionType
from app.services.transactions import default_classification

WINDOW = timedelta(days=1)


def _is_two_sides_of_a_transfer(row: models.Transaction, other: models.Transaction) -> bool:
    """A transfer and an income: the way two notices of the same transfer look when both come from the bank."""
    return {row.type, other.type} == {TransactionType.TRANSFER.value, TransactionType.INCOME.value}


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
            models.Transaction.date >= row.date - WINDOW,
            models.Transaction.date <= row.date + WINDOW,
        )
    )
    # Another source, or the two sides of a transfer that one source announced twice.
    related = [other for other in found if other.source != row.source or _is_two_sides_of_a_transfer(row, other)]
    return sorted(related, key=lambda other: abs(other.date - row.date))


def merge(db: Session, absorbed_id: uuid.UUID, into_id: uuid.UUID) -> models.Transaction:
    """Say that a pending movement is the same as another: keep the other, complete it, set this one aside."""
    if absorbed_id == into_id:
        raise ApiError(422, "same_movement", "Elige otro movimiento: no se puede unir consigo mismo.")
    # Both rows are locked in a fixed order, so two merges at once cannot both succeed and leave nothing behind.
    rows = {
        row.id: row
        for row in db.scalars(
            select(models.Transaction)
            .where(models.Transaction.id.in_([absorbed_id, into_id]))
            .order_by(models.Transaction.id)
            .with_for_update()
        )
    }
    absorbed, kept = rows.get(absorbed_id), rows.get(into_id)
    if absorbed is None or kept is None:
        raise ApiError(404, "not_found", "El movimiento no existe.")
    if absorbed.status != TransactionStatus.PENDING_REVIEW.value:
        raise ApiError(409, "not_pending", "Solo se puede unir un movimiento pendiente de revisión.")
    if kept.status == TransactionStatus.DISCARDED.value:
        raise ApiError(409, "already_discarded", "Ese movimiento está descartado.")
    if (absorbed.amount, absorbed.currency) != (kept.amount, kept.currency):
        raise ApiError(422, "not_the_same_amount", "Los dos movimientos deben tener el mismo monto y la misma moneda.")
    if kept.type == TransactionType.INCOME.value and absorbed.type == TransactionType.TRANSFER.value:
        raise ApiError(
            409,
            "merge_the_other_way",
            "Une el ingreso dentro de la transferencia, no al revés: la transferencia es la que lleva el origen y el destino.",
        )

    _complete(db, kept, absorbed)
    # Set aside, not deleted: it keeps its hash, so the same notification cannot come back as a new movement.
    absorbed.status = TransactionStatus.DISCARDED.value
    db.commit()
    return kept


def _complete(db: Session, kept: models.Transaction, absorbed: models.Transaction) -> None:
    """Fill in what the kept movement lacks with what the other one knows. What it has is never replaced.

    A movement that is already confirmed counts in the balances: it is not changed, except for its merchant, so
    joining never moves money. Everything else is only completed on a pending one.
    """
    if not kept.merchant and absorbed.merchant:
        kept.merchant = absorbed.merchant
    if kept.status == TransactionStatus.CONFIRMED.value:
        return

    if kept.type != TransactionType.TRANSFER.value:
        if kept.account_id is None and absorbed.account_id is not None:
            kept.account_id = absorbed.account_id
        if kept.category_id is None and absorbed.category_id is not None and kept.type == absorbed.type:
            kept.category_id = absorbed.category_id
        return

    # The source of a transfer: the account of the other record, if it cannot be the destination too.
    if kept.account_id is None and absorbed.account_id not in (None, kept.target_account_id):
        if _same_currency(db, absorbed.account_id, kept.currency):
            kept.account_id = absorbed.account_id

    # Its destination: the one the other transfer knew, or the account that received it as an income.
    destination = absorbed.target_account_id
    if absorbed.type == TransactionType.INCOME.value:
        destination = absorbed.account_id
    if (
        kept.target_account_id is None
        and destination is not None
        and destination != kept.account_id
        and kept.classification != Classification.EXPENSE.value
        and _same_currency(db, destination, kept.currency)
    ):
        kept.target_account_id = destination
        kept.target_text = None
        kept.target_amount, kept.fx_rate = None, None

    if kept.account_id is not None and kept.target_account_id is not None and kept.classification in (
        None,
        Classification.OWN_TRANSFER.value,
    ):
        source, target = db.get(models.Account, kept.account_id), db.get(models.Account, kept.target_account_id)
        kept.classification = default_classification(AccountType(source.type), AccountType(target.type)).value


def _same_currency(db: Session, account_id: uuid.UUID, currency: str) -> bool:
    account = db.get(models.Account, account_id)
    return account is not None and account.currency == currency
