import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.adjustments import plan_adjustment
from app.domain.entities import (
    LOCAL_TIMEZONE,
    AccountType,
    Classification,
    Currency,
    TransactionStatus,
    TransactionType,
    local_date,
)
from app.domain.errors import DomainError
from app.domain.fx import round_money
from app.schemas.transactions import AdjustmentCreate, AdjustmentResult, TransactionCreate, TransactionOut, TransactionUpdate
from app.services.accounts import get_account
from app.services.balances import account_balances
from app.services.common import get_or_404, require

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
RATE_PRECISION = Decimal("0.0001")
ADJUSTMENT_TYPES = (TransactionType.ADJUSTMENT_IN, TransactionType.ADJUSTMENT_OUT)


@dataclass
class Draft:
    """The full state of a movement that is about to be saved, whether new or edited."""

    account_id: uuid.UUID
    type: TransactionType
    amount: Decimal
    date: datetime
    category_id: uuid.UUID | None = None
    merchant: str | None = None
    note: str | None = None
    target_account_id: uuid.UUID | None = None
    target_amount: Decimal | None = None
    classification: Classification | None = None


def get_transaction(db: Session, transaction_id: uuid.UUID) -> models.Transaction:
    return get_or_404(db, models.Transaction, transaction_id, "El movimiento no existe.")


def create_transaction(db: Session, data: TransactionCreate) -> models.Transaction:
    draft = Draft(
        account_id=data.account_id,
        type=data.type,
        amount=data.amount,
        date=data.date or datetime.now(UTC),
        category_id=data.category_id,
        merchant=data.merchant,
        note=data.note,
        target_account_id=data.target_account_id,
        target_amount=data.target_amount,
        classification=data.classification,
    )
    values = _prepare(db, draft, check_archived=True)

    row = models.Transaction(
        id=uuid.uuid4(), source="manual", status=TransactionStatus.CONFIRMED.value, **values
    )
    db.add(row)
    db.commit()
    return row


def update_transaction(db: Session, transaction_id: uuid.UUID, data: TransactionUpdate) -> models.Transaction:
    row = get_transaction(db, transaction_id)
    changes = data.changes()

    draft = Draft(
        account_id=changes.get("account_id", row.account_id),
        type=TransactionType(row.type),
        amount=changes.get("amount", row.amount),
        date=changes.get("date", row.date),
        category_id=changes.get("category_id", row.category_id),
        merchant=changes.get("merchant", row.merchant),
        note=changes.get("note", row.note),
        target_account_id=changes.get("target_account_id", row.target_account_id),
        target_amount=changes.get("target_amount"),
        classification=changes.get(
            "classification",
            # A new destination account gets a fresh default classification.
            None if "target_account_id" in changes else (Classification(row.classification) if row.classification else None),
        ),
    )
    values = _prepare(db, draft, check_archived="account_id" in changes and changes["account_id"] != row.account_id)

    # Editing only text fields must not recompute a stored conversion.
    conversion_inputs = {"amount", "date", "account_id", "target_account_id", "target_amount"}
    if not changes.keys() & conversion_inputs and values["target_amount"] is not None:
        values["target_amount"] = row.target_amount
        values["fx_rate"] = row.fx_rate

    for field, value in values.items():
        setattr(row, field, value)
    db.commit()
    return row


def delete_transaction(db: Session, transaction_id: uuid.UUID) -> None:
    row = get_transaction(db, transaction_id)
    if row.source != "manual":
        raise ApiError(
            409,
            "use_discard",
            "Este movimiento viene de una fuente automática. Descártalo en lugar de borrarlo.",
        )
    db.delete(row)
    db.commit()


def confirm_transaction(db: Session, transaction_id: uuid.UUID) -> models.Transaction:
    row = get_transaction(db, transaction_id)
    if row.status != TransactionStatus.PENDING_REVIEW:
        raise ApiError(409, "not_pending", "Solo se pueden confirmar movimientos pendientes de revisión.")
    row.status = TransactionStatus.CONFIRMED.value
    db.commit()
    return row


def discard_transaction(db: Session, transaction_id: uuid.UUID) -> models.Transaction:
    row = get_transaction(db, transaction_id)
    if row.status == TransactionStatus.DISCARDED:
        raise ApiError(409, "already_discarded", "El movimiento ya está descartado.")
    row.status = TransactionStatus.DISCARDED.value
    db.commit()
    return row


@dataclass
class TransactionFilters:
    date_from: date | None = None
    date_to: date | None = None
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    type: TransactionType | None = None
    status: TransactionStatus | None = None
    text: str | None = None


def list_transactions(
    db: Session, filters: TransactionFilters, cursor: str | None, limit: int
) -> tuple[list[models.Transaction], str | None]:
    """Newest first. Pagination is by cursor, so rows added meanwhile do not shift the pages."""
    query = select(models.Transaction)

    if filters.date_from is not None:
        query = query.where(models.Transaction.date >= _start_of_day(filters.date_from))
    if filters.date_to is not None:
        query = query.where(models.Transaction.date < _start_of_day(filters.date_to + timedelta(days=1)))
    if filters.account_id is not None:
        query = query.where(
            or_(
                models.Transaction.account_id == filters.account_id,
                models.Transaction.target_account_id == filters.account_id,
            )
        )
    if filters.category_id is not None:
        query = query.where(models.Transaction.category_id == filters.category_id)
    if filters.type is not None:
        query = query.where(models.Transaction.type == filters.type.value)
    if filters.status is not None:
        query = query.where(models.Transaction.status == filters.status.value)
    if filters.text:
        pattern = "%" + filters.text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            or_(
                models.Transaction.merchant.ilike(pattern, escape="\\"),
                models.Transaction.note.ilike(pattern, escape="\\"),
            )
        )
    if cursor is not None:
        cursor_date, cursor_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                models.Transaction.date < cursor_date,
                and_(models.Transaction.date == cursor_date, models.Transaction.id < cursor_id),
            )
        )

    rows = list(
        db.scalars(query.order_by(models.Transaction.date.desc(), models.Transaction.id.desc()).limit(limit + 1))
    )
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1])
    return rows, next_cursor


def create_adjustment(db: Session, account_id: uuid.UUID, data: AdjustmentCreate) -> AdjustmentResult:
    """Record the movement that takes the account's balance to the value the user observes."""
    account = get_account(db, account_id)
    if account.archived:
        raise ApiError(409, "account_archived", "La cuenta está archivada.")

    balance = account_balances(db, {account.id})[account.id]
    try:
        plan = plan_adjustment(balance, data.observed_balance, data.note)
    except DomainError:
        raise ApiError(422, "adjustment_note_required", "Escribe por qué ajustas el saldo.") from None

    if plan is None:
        return AdjustmentResult(transaction=None, balance=balance)

    row = models.Transaction(
        id=uuid.uuid4(),
        account_id=account.id,
        type=plan.type.value,
        amount=plan.amount,
        currency=account.currency,
        date=data.date or datetime.now(UTC),
        note=plan.note,
        source="manual",
        status=TransactionStatus.CONFIRMED.value,
    )
    db.add(row)
    db.commit()
    return AdjustmentResult(transaction=TransactionOut.model_validate(row), balance=round_money(data.observed_balance))


def _prepare(db: Session, draft: Draft, check_archived: bool) -> dict[str, Any]:
    """Validate a movement and work out the stored fields that depend on the rest."""
    source = require(db, models.Account, draft.account_id, "account_not_found", "La cuenta no existe.")
    if check_archived and source.archived:
        raise ApiError(409, "account_archived", "La cuenta está archivada.")

    values: dict[str, Any] = {
        "account_id": source.id,
        "type": draft.type.value,
        "amount": draft.amount,
        "currency": source.currency,
        "date": draft.date,
        "merchant": draft.merchant,
        "note": draft.note,
        "category_id": draft.category_id,
    }

    if draft.type is TransactionType.TRANSFER:
        values.update(_prepare_transfer(db, source, draft))
    else:
        if draft.target_account_id or draft.target_amount or draft.classification:
            raise ApiError(
                422,
                "transfer_only_field",
                "El destino, el monto recibido y la clasificación solo aplican a transferencias.",
            )
        values.update(target_account_id=None, target_amount=None, fx_rate=None, classification=None)

    if draft.type in ADJUSTMENT_TYPES and not (draft.note and draft.note.strip()):
        raise ApiError(422, "adjustment_note_required", "Escribe por qué ajustas el saldo.")

    classification = Classification(values["classification"]) if values["classification"] else None
    _check_category(db, draft.category_id, draft.type, classification)
    return values


def _prepare_transfer(db: Session, source: models.Account, draft: Draft) -> dict[str, Any]:
    classification = draft.classification

    if draft.target_account_id is None:
        if draft.target_amount is not None:
            raise ApiError(422, "target_amount_not_allowed", "El monto recibido solo aplica con una cuenta de destino.")
        if classification is Classification.LOAN or AccountType(source.type) is AccountType.LOAN:
            raise ApiError(422, "loan_account_mismatch", "Un préstamo necesita la cuenta de destino.")
        return {
            "target_account_id": None,
            "target_amount": None,
            "fx_rate": None,
            "classification": classification.value if classification else None,
        }

    target = require(
        db, models.Account, draft.target_account_id, "target_account_not_found", "La cuenta de destino no existe."
    )
    if target.id == source.id:
        raise ApiError(422, "same_account", "El origen y el destino no pueden ser la misma cuenta.")

    source_type, target_type = AccountType(source.type), AccountType(target.type)
    involves_loan = AccountType.LOAN in (source_type, target_type)
    if classification is None:
        if involves_loan:
            classification = Classification.LOAN
        elif target_type is AccountType.CREDIT_CARD:
            classification = Classification.PAYMENT
        else:
            classification = Classification.OWN_TRANSFER
    if (classification is Classification.LOAN) != involves_loan:
        raise ApiError(
            422,
            "loan_account_mismatch",
            "Un préstamo debe pasar por una cuenta de préstamo, y esas cuentas solo admiten préstamos.",
        )

    target_amount, fx_rate = _convert(db, source, target, draft)
    return {
        "target_account_id": target.id,
        "target_amount": target_amount,
        "fx_rate": fx_rate,
        "classification": classification.value,
    }


def _convert(
    db: Session, source: models.Account, target: models.Account, draft: Draft
) -> tuple[Decimal | None, Decimal | None]:
    """Amount received and rate used when the two accounts have different currencies."""
    if source.currency == target.currency:
        if draft.target_amount is not None:
            raise ApiError(422, "target_amount_not_allowed", "Las dos cuentas tienen la misma moneda.")
        return None, None

    source_is_cop = source.currency == Currency.COP
    if draft.target_amount is not None:
        cop, foreign = (draft.amount, draft.target_amount) if source_is_cop else (draft.target_amount, draft.amount)
        return draft.target_amount, (cop / foreign).quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)

    rate = _latest_rate(db, Currency.USD, local_date(draft.date))
    if rate is None:
        raise ApiError(
            422,
            "fx_rate_unavailable",
            "No hay TRM para esa fecha. Escribe el monto que recibe la cuenta de destino.",
        )
    received = draft.amount / rate if source_is_cop else draft.amount * rate
    return round_money(received), rate


def _latest_rate(db: Session, currency: Currency, day: date) -> Decimal | None:
    """Rate of the day, or of the closest earlier day (weekends and holidays have none)."""
    return db.scalar(
        select(models.FxRate.value)
        .where(models.FxRate.currency == currency.value, models.FxRate.date <= day)
        .order_by(models.FxRate.date.desc())
        .limit(1)
    )


def _check_category(
    db: Session, category_id: uuid.UUID | None, transaction_type: TransactionType, classification: Classification | None
) -> None:
    if category_id is None:
        return
    if transaction_type in ADJUSTMENT_TYPES:
        raise ApiError(422, "category_not_allowed", "Un ajuste de saldo no lleva categoría.")

    category = require(db, models.Category, category_id, "category_not_found", "La categoría no existe.")
    # A transfer classified as an expense counts as one, so it uses expense categories.
    if transaction_type is TransactionType.INCOME:
        expected = "income"
    elif transaction_type is TransactionType.EXPENSE or classification is Classification.EXPENSE:
        expected = "expense"
    else:
        expected = "transfer"
    if category.type != expected:
        raise ApiError(
            422, "category_type_mismatch", "La categoría no corresponde al tipo de movimiento.", {"expected": expected}
        )


def _start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=LOCAL_TIMEZONE)


def _encode_cursor(row: models.Transaction) -> str:
    return base64.urlsafe_b64encode(f"{row.date.isoformat()}|{row.id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        moment, row_id = raw.split("|")
        return datetime.fromisoformat(moment), uuid.UUID(row_id)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise ApiError(422, "invalid_cursor", "El cursor de paginación no es válido.") from None
