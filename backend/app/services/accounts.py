import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.entities import AccountType
from app.schemas.accounts import AccountCreate, AccountOut, AccountUpdate, IdentifierIn
from app.services.balances import account_balances
from app.services.common import get_or_404

# Types the user can switch between. Loan, exchange and system accounts behave differently
# (they are left out of real money or of the flow), so converting to or from them is not allowed.
SWITCHABLE_TYPES = {
    AccountType.CASH,
    AccountType.BANK,
    AccountType.SAVINGS,
    AccountType.WALLET,
    AccountType.CREDIT_CARD,
}


def to_out(row: models.Account, balance: Decimal) -> AccountOut:
    return AccountOut(
        id=row.id,
        name=row.name,
        type=AccountType(row.type),
        currency=row.currency,
        initial_balance=row.initial_balance,
        counterparty=row.counterparty,
        key=row.key,
        archived=row.archived,
        balance=balance,
    )


def get_account(db: Session, account_id: uuid.UUID) -> models.Account:
    return get_or_404(db, models.Account, account_id, "La cuenta no existe.")


def list_accounts(db: Session, archived: bool | None) -> list[AccountOut]:
    query = select(models.Account).order_by(models.Account.name)
    if archived is not None:
        query = query.where(models.Account.archived == archived)
    rows = list(db.scalars(query))
    balances = account_balances(db)
    return [to_out(row, balances[row.id]) for row in rows]


def get_account_out(db: Session, account_id: uuid.UUID) -> AccountOut:
    row = get_account(db, account_id)
    return to_out(row, account_balances(db, {row.id})[row.id])


def create_account(db: Session, data: AccountCreate) -> AccountOut:
    if data.type is AccountType.SYSTEM:
        raise ApiError(422, "invalid_account_type", "Las cuentas de sistema las crea la aplicación.")
    _check_counterparty(data.type, data.counterparty)
    _check_key_is_free(db, data.key, exclude=None)

    row = models.Account(
        id=uuid.uuid4(),
        name=data.name,
        type=data.type.value,
        currency=data.currency.value,
        initial_balance=data.initial_balance,
        counterparty=data.counterparty,
        key=data.key,
        archived=False,
    )
    db.add(row)
    _commit(db)
    return to_out(row, row.initial_balance)


def update_account(db: Session, account_id: uuid.UUID, data: AccountUpdate) -> AccountOut:
    row = get_account(db, account_id)
    changes = data.changes()

    new_type = changes.get("type", AccountType(row.type))
    if new_type is not AccountType(row.type):
        if new_type not in SWITCHABLE_TYPES or AccountType(row.type) not in SWITCHABLE_TYPES:
            raise ApiError(
                422, "account_type_locked", "Este tipo de cuenta no se puede cambiar por el tipo elegido."
            )
    _check_counterparty(new_type, changes.get("counterparty", row.counterparty))
    if "key" in changes:
        _check_key_is_free(db, changes["key"], exclude=row.id)

    for name, value in changes.items():
        setattr(row, name, value.value if isinstance(value, AccountType) else value)
    _commit(db)
    return to_out(row, account_balances(db, {row.id})[row.id])


def list_identifiers(db: Session, account_id: uuid.UUID) -> list[models.AccountIdentifier]:
    get_account(db, account_id)
    return list(
        db.scalars(
            select(models.AccountIdentifier)
            .where(models.AccountIdentifier.account_id == account_id)
            .order_by(models.AccountIdentifier.digits)
        )
    )


def replace_identifiers(
    db: Session, account_id: uuid.UUID, identifiers: list[IdentifierIn]
) -> list[models.AccountIdentifier]:
    """Replace the whole list.

    The same last digits cannot point to two accounts of the same currency, because a notification
    could not tell them apart. A card with purchases in pesos and in dollars has one account per
    currency, and both can carry the same digits.
    """
    account = get_account(db, account_id)

    digits = [item.digits for item in identifiers]
    if len(set(digits)) != len(digits):
        raise ApiError(422, "duplicate_identifier", "Hay dígitos repetidos en la lista.")

    taken = list(
        db.scalars(
            select(models.AccountIdentifier.digits)
            .join(models.Account, models.Account.id == models.AccountIdentifier.account_id)
            .where(
                models.AccountIdentifier.digits.in_(digits),
                models.AccountIdentifier.account_id != account_id,
                models.Account.currency == account.currency,
            )
        )
    )
    if taken:
        raise ApiError(
            409,
            "identifier_taken",
            "Esos dígitos ya pertenecen a otra cuenta.",
            {"digits": sorted(set(taken))},
        )

    db.query(models.AccountIdentifier).filter(models.AccountIdentifier.account_id == account_id).delete()
    rows = [
        models.AccountIdentifier(id=uuid.uuid4(), account_id=account_id, digits=item.digits, type=item.type)
        for item in identifiers
    ]
    db.add_all(rows)
    _commit(db)
    return sorted(rows, key=lambda row: row.digits)


def _check_counterparty(account_type: AccountType, counterparty: str | None) -> None:
    if account_type is AccountType.LOAN and not counterparty:
        raise ApiError(422, "counterparty_required", "Una cuenta de préstamo necesita el nombre de la persona.")
    if account_type is not AccountType.LOAN and counterparty:
        raise ApiError(422, "counterparty_not_allowed", "Solo las cuentas de préstamo tienen contraparte.")


def _check_key_is_free(db: Session, key: str | None, exclude: uuid.UUID | None) -> None:
    if key is None:
        return
    query = select(models.Account.id).where(models.Account.key == key)
    if exclude is not None:
        query = query.where(models.Account.id != exclude)
    if db.scalar(query) is not None:
        raise ApiError(409, "account_key_taken", "Esa llave ya está registrada en otra cuenta.")


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "conflict", "Los datos chocan con algo que ya existe.") from None
