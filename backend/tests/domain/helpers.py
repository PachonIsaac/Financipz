import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.entities import (
    Account,
    AccountType,
    Classification,
    Currency,
    Transaction,
    TransactionStatus,
    TransactionType,
)

D = Decimal
BOGOTA = ZoneInfo("America/Bogota")
NOON = datetime(2026, 10, 15, 12, 0, tzinfo=BOGOTA)


def make_account(
    type: AccountType = AccountType.BANK,
    currency: Currency = Currency.COP,
    initial: str | int = 0,
    archived: bool = False,
) -> Account:
    return Account(
        id=uuid.uuid4(),
        type=type,
        currency=currency,
        initial_balance=D(str(initial)),
        archived=archived,
    )


def make_transaction(
    account: Account,
    type: TransactionType,
    amount: str | int,
    *,
    currency: Currency | None = None,
    when: datetime = NOON,
    status: TransactionStatus = TransactionStatus.CONFIRMED,
    target: Account | None = None,
    target_amount: str | int | None = None,
    classification: Classification | None = None,
    category: uuid.UUID | None = None,
) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        account_id=account.id,
        type=type,
        amount=D(str(amount)),
        currency=currency or account.currency,
        date=when,
        status=status,
        target_account_id=target.id if target else None,
        target_amount=D(str(target_amount)) if target_amount is not None else None,
        classification=classification,
        category_id=category,
    )
