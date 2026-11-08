import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.entities import AccountType, Currency, TransactionStatus, TransactionType
from app.domain.envelopes import months_left, next_year, suggested_monthly
from app.domain.periods import local_today
from app.schemas.envelopes import (
    EntryCreate,
    EnvelopeCreate,
    EnvelopeList,
    EnvelopeOut,
    EnvelopePay,
    EnvelopeUpdate,
    PayResult,
)
from app.schemas.transactions import TransactionCreate
from app.services import transactions as transaction_service
from app.services.balances import account_balances
from app.services.common import get_or_404, require

# Money can only be set apart in accounts the user spends from.
ENVELOPE_ACCOUNT_TYPES = frozenset(
    {AccountType.CASH.value, AccountType.BANK.value, AccountType.SAVINGS.value, AccountType.WALLET.value}
)


def _held(db: Session, envelope_ids: list[uuid.UUID] | None = None) -> dict[uuid.UUID, Decimal]:
    query = select(models.EnvelopeEntry.envelope_id, func.sum(models.EnvelopeEntry.amount)).group_by(
        models.EnvelopeEntry.envelope_id
    )
    if envelope_ids is not None:
        query = query.where(models.EnvelopeEntry.envelope_id.in_(envelope_ids))
    return {envelope_id: total for envelope_id, total in db.execute(query)}


def _reserved_per_account(db: Session) -> dict[uuid.UUID, Decimal]:
    """Everything the envelopes hold, per account, without capping it to the balance."""
    rows = db.execute(
        select(models.Envelope.account_id, func.sum(models.EnvelopeEntry.amount))
        .join(models.EnvelopeEntry, models.EnvelopeEntry.envelope_id == models.Envelope.id)
        .group_by(models.Envelope.account_id)
    )
    return {account_id: total for account_id, total in rows}


def _to_out(
    row: models.Envelope,
    account: models.Account,
    held: Decimal,
    shortfall: Decimal,
    today: date,
) -> EnvelopeOut:
    suggestion = suggested_monthly(row.target_amount, held, row.due_date, today)
    return EnvelopeOut(
        id=row.id,
        account_id=row.account_id,
        account_name=account.name,
        currency=account.currency,
        name=row.name,
        target_amount=row.target_amount,
        due_date=row.due_date,
        repeats_yearly=row.repeats_yearly,
        balance=held,
        months_left=months_left(today, row.due_date) if row.due_date else None,
        suggested_monthly=suggestion,
        ready=row.target_amount is not None and held >= row.target_amount,
        shortfall=shortfall,
    )


def _shortfalls(db: Session, accounts: set[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    if not accounts:
        return {}
    balances = account_balances(db, accounts)
    reserved = _reserved_per_account(db)
    return {
        account_id: max(reserved.get(account_id, Decimal(0)) - max(balances[account_id], Decimal(0)), Decimal(0))
        for account_id in accounts
    }


def list_envelopes(db: Session) -> EnvelopeList:
    rows = list(
        db.scalars(
            select(models.Envelope)
            .where(models.Envelope.archived.is_(False))
            .order_by(models.Envelope.due_date.asc().nulls_last(), models.Envelope.name)
        )
    )
    accounts = {account.id: account for account in db.scalars(select(models.Account))}
    held = _held(db)
    shortfalls = _shortfalls(db, {row.account_id for row in rows})
    today = local_today()
    items = [
        _to_out(row, accounts[row.account_id], held.get(row.id, Decimal(0)), shortfalls[row.account_id], today)
        for row in rows
    ]
    in_pesos = [item for item in items if item.currency == Currency.COP.value]
    return EnvelopeList(
        envelopes=items,
        reserved_total=sum((item.balance for item in in_pesos), Decimal(0)),
        suggested_total=sum((item.suggested_monthly or Decimal(0) for item in in_pesos), Decimal(0)),
    )


def get_envelope(db: Session, envelope_id: uuid.UUID) -> models.Envelope:
    return get_or_404(db, models.Envelope, envelope_id, "La cajita no existe.")


def envelope_out(db: Session, row: models.Envelope) -> EnvelopeOut:
    account = db.get(models.Account, row.account_id)
    held = _held(db, [row.id]).get(row.id, Decimal(0))
    shortfall = _shortfalls(db, {row.account_id})[row.account_id]
    return _to_out(row, account, held, shortfall, local_today())


def _check_account(account: models.Account) -> None:
    if account.type not in ENVELOPE_ACCOUNT_TYPES:
        raise ApiError(422, "invalid_envelope_account", "Solo puedes apartar plata en cuentas de dinero que gastas.")
    if account.archived:
        raise ApiError(409, "account_archived", "La cuenta está archivada.")


def create_envelope(db: Session, data: EnvelopeCreate) -> EnvelopeOut:
    account = require(db, models.Account, data.account_id, "account_not_found", "La cuenta no existe.")
    _check_account(account)
    row = models.Envelope(
        id=uuid.uuid4(),
        account_id=account.id,
        name=data.name,
        target_amount=data.target_amount,
        due_date=data.due_date,
        repeats_yearly=data.repeats_yearly,
        archived=False,
    )
    db.add(row)
    db.commit()
    return envelope_out(db, row)


def update_envelope(db: Session, envelope_id: uuid.UUID, data: EnvelopeUpdate) -> EnvelopeOut:
    row = get_envelope(db, envelope_id)
    for name, value in data.changes().items():
        setattr(row, name, value)
    db.commit()
    return envelope_out(db, row)


def archive_envelope(db: Session, envelope_id: uuid.UUID) -> None:
    row = get_envelope(db, envelope_id)
    if _held(db, [row.id]).get(row.id, Decimal(0)) != 0:
        raise ApiError(409, "envelope_not_empty", "Libera o paga lo que tiene la cajita antes de borrarla.")
    row.archived = True
    db.commit()


def _available(db: Session, account_id: uuid.UUID) -> Decimal:
    """What the account holds that no envelope has set apart."""
    balance = account_balances(db, {account_id})[account_id]
    return balance - _reserved_per_account(db).get(account_id, Decimal(0))


def add_entry(db: Session, envelope_id: uuid.UUID, data: EntryCreate) -> EnvelopeOut:
    row = get_envelope(db, envelope_id)
    if row.archived:
        raise ApiError(409, "envelope_archived", "La cajita está borrada.")
    held = _held(db, [row.id]).get(row.id, Decimal(0))
    if data.kind == "contribute":
        _check_account(db.get(models.Account, row.account_id))
        available = _available(db, row.account_id)
        if data.amount > available:
            raise ApiError(
                409,
                "insufficient_available",
                "No hay tanto disponible en la cuenta: lo demás ya está apartado.",
                {"available": str(max(available, Decimal(0)))},
            )
        amount = data.amount
    else:
        if data.amount > held:
            raise ApiError(409, "insufficient_envelope", "La cajita no tiene tanto.", {"balance": str(held)})
        amount = -data.amount
    db.add(models.EnvelopeEntry(id=uuid.uuid4(), envelope_id=row.id, amount=amount, date=local_today(), note=data.note))
    db.commit()
    return envelope_out(db, row)


def list_entries(db: Session, envelope_id: uuid.UUID) -> list[models.EnvelopeEntry]:
    get_envelope(db, envelope_id)
    return list(
        db.scalars(
            select(models.EnvelopeEntry)
            .where(models.EnvelopeEntry.envelope_id == envelope_id)
            .order_by(models.EnvelopeEntry.date.desc(), models.EnvelopeEntry.created_at.desc())
        )
    )


def pay(db: Session, envelope_id: uuid.UUID, data: EnvelopePay) -> PayResult:
    """Record the payment as a normal expense and free that amount from the envelope.

    If the payment is larger than what the envelope holds, the rest simply comes out of the available money.
    """
    envelope = get_envelope(db, envelope_id)
    if envelope.archived:
        raise ApiError(409, "envelope_archived", "La cajita está borrada.")
    account = db.get(models.Account, envelope.account_id)

    if data.transaction_id is not None:
        # Locked until the end, so two taps on the same payment cannot free the money twice.
        tx = db.scalar(
            select(models.Transaction).where(models.Transaction.id == data.transaction_id).with_for_update()
        )
        if tx is None:
            raise ApiError(404, "not_found", "El movimiento no existe.")
        if tx.type != TransactionType.EXPENSE.value or tx.status == TransactionStatus.DISCARDED.value:
            raise ApiError(422, "not_an_expense", "Solo se puede pagar con la cajita un gasto vigente.")
        if tx.account_id is None:
            raise ApiError(409, "account_required", "Elige primero la cuenta del gasto.")
        already = db.scalar(
            select(func.count()).select_from(models.EnvelopeEntry).where(models.EnvelopeEntry.transaction_id == tx.id)
        )
        if already:
            raise ApiError(409, "already_paid", "Este gasto ya se pagó con una cajita.")
        if tx.currency != account.currency:
            raise ApiError(422, "currency_mismatch", "El gasto está en otra moneda que la cuenta de la cajita.")
        if tx.status == TransactionStatus.PENDING_REVIEW.value:
            transaction_service.confirm_transaction(db, tx.id, commit=False)
        paid = tx.amount
        transaction_id = tx.id
    else:
        expense = data.expense
        paying_account = require(db, models.Account, expense.account_id, "account_not_found", "La cuenta no existe.")
        if paying_account.currency != account.currency:
            raise ApiError(422, "currency_mismatch", "El gasto está en otra moneda que la cuenta de la cajita.")
        created = transaction_service.create_transaction(
            db,
            TransactionCreate(
                account_id=expense.account_id,
                type=TransactionType.EXPENSE,
                amount=expense.amount,
                date=expense.date,
                category_id=expense.category_id,
                merchant=expense.merchant or envelope.name,
                note=expense.note,
            ),
            commit=False,
        )
        paid = created.amount
        transaction_id = created.id

    held = _held(db, [envelope.id]).get(envelope.id, Decimal(0))
    freed = min(paid, max(held, Decimal(0)))
    if freed > 0:
        db.add(
            models.EnvelopeEntry(
                id=uuid.uuid4(),
                envelope_id=envelope.id,
                amount=-freed,
                date=local_today(),
                note=None,
                transaction_id=transaction_id,
            )
        )
    # Only a payment that really used the envelope closes the cycle; a date far in the past catches up.
    if freed > 0 and envelope.repeats_yearly and envelope.due_date is not None:
        envelope.due_date = next_year(envelope.due_date)
        while envelope.due_date < local_today():
            envelope.due_date = next_year(envelope.due_date)
    db.commit()
    return PayResult(envelope=envelope_out(db, envelope), transaction_id=transaction_id, freed=freed)
