"""Turns what a parser recognized into a movement that waits for review.

Every automatic source (an email, an SMS) ends here. Nothing is confirmed on its own: the movement is
stored as pending, so it does not count in the balances or the summary until the person confirms it. The
same notification arriving twice is recognized by its hash and stored once. What the notification does not
say (which account, what a transfer to a stranger was) is left empty for the person to fill in, never guessed.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models
from app.domain.entities import LOCAL_TIMEZONE, AccountType, Classification, Currency, TransactionStatus, TransactionType
from app.parsers.dedupe import dedupe_hash_for
from app.parsers.models import NotificationKind, NotificationSource, ParsedNotification
from app.services.transactions import default_classification


class Outcome(StrEnum):
    CREATED = "created"
    # The same notification was already stored; `transaction` is the one that exists.
    DUPLICATE = "duplicate"
    # Recognized, and not a money movement (a failed purchase, a security notice).
    IGNORED = "ignored"
    # Nothing in it could be used: no form matched, or it lacks an amount or a day.
    UNRECOGNIZED = "unrecognized"


@dataclass(frozen=True)
class IngestResult:
    outcome: Outcome
    transaction: models.Transaction | None = None


# Where the money of an income without digits goes, when the person has exactly one such account.
_SAVINGS = (AccountType.SAVINGS,)
_WALLET = (AccountType.WALLET,)
_CASH = (AccountType.CASH,)

# Names of the categories that Ualá's daily return and card bonus belong to (RF-31).
_CATEGORY_NAMES = {
    NotificationKind.YIELD: "rendimiento",
    NotificationKind.CARD_BONUS: "bonificaci",
}


def ingest(db: Session, parsed: ParsedNotification | None) -> IngestResult:
    """Store a recognized notification as a pending movement. `None` is a text no parser understood."""
    if parsed is None:
        return IngestResult(Outcome.UNRECOGNIZED)
    if not parsed.is_movement:
        return IngestResult(Outcome.IGNORED)

    digest = dedupe_hash_for(parsed)
    moment = _moment(parsed)
    if digest is None or moment is None or parsed.amount is None or parsed.amount <= 0 or parsed.currency is None:
        return IngestResult(Outcome.UNRECOGNIZED)

    existing = _by_hash(db, digest)
    if existing is not None:
        return IngestResult(Outcome.DUPLICATE, existing)

    row = _build(db, parsed, digest, moment)
    try:
        # A savepoint, so losing a race for the same hash leaves the caller's transaction usable.
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = _by_hash(db, digest)
        if existing is None:
            raise
        return IngestResult(Outcome.DUPLICATE, existing)
    db.commit()
    return IngestResult(Outcome.CREATED, row)


def _by_hash(db: Session, digest: str) -> models.Transaction | None:
    return db.scalars(select(models.Transaction).where(models.Transaction.dedupe_hash == digest).limit(1)).first()


def _moment(parsed: ParsedNotification) -> datetime | None:
    if parsed.occurred_at is not None:
        return parsed.occurred_at
    if parsed.occurred_on is not None:
        # A day without a time: midday keeps it on that day in any timezone.
        return datetime.combine(parsed.occurred_on, time(12, 0), tzinfo=LOCAL_TIMEZONE)
    return None


def _build(db: Session, parsed: ParsedNotification, digest: str, moment: datetime) -> models.Transaction:
    assert parsed.amount is not None and parsed.currency is not None
    currency = parsed.currency
    kind = parsed.kind

    account: models.Account | None
    target: models.Account | None = None
    transaction_type = parsed.suggested_type or TransactionType.EXPENSE
    classification: Classification | None = None
    target_text = parsed.target_text

    if kind is NotificationKind.TOP_UP:
        # Money coming into the wallet from a bank account the SMS does not name.
        account = None
        target = _only_account(db, _WALLET, currency)
        transaction_type = TransactionType.TRANSFER
        classification = Classification.OWN_TRANSFER
    elif kind is NotificationKind.WITHDRAWAL:
        account = _by_digits(db, parsed.last_digits, currency)
        target = _only_account(db, _CASH, currency)
        transaction_type = TransactionType.TRANSFER
    elif kind is NotificationKind.TRANSFER_OUT:
        account = _by_digits(db, parsed.last_digits, currency)
        target = _own_destination(db, parsed.target_text, currency)
        transaction_type = TransactionType.TRANSFER
    elif kind is NotificationKind.PAYROLL:
        account = _only_account(db, _SAVINGS, currency)
    elif kind in (NotificationKind.YIELD, NotificationKind.CARD_BONUS):
        account = _only_account(db, _WALLET, currency)
    else:
        account = _by_digits(db, parsed.last_digits, currency)
        if account is None and parsed.last_digits is None and parsed.source is NotificationSource.SMS_UALA:
            # Ualá's SMS carry no digits: they are about the wallet, if the person has only one.
            account = _only_account(db, _WALLET, currency)

    if transaction_type is TransactionType.TRANSFER:
        if target is not None and account is not None and target.id == account.id:
            target = None
        if target is not None:
            target_text = None
            if classification is None and account is not None:
                classification = default_classification(AccountType(account.type), AccountType(target.type))
            elif classification is None:
                classification = Classification.OWN_TRANSFER
    else:
        target = None
        target_text = None

    return models.Transaction(
        id=uuid.uuid4(),
        account_id=account.id if account else None,
        target_account_id=target.id if target else None,
        target_text=target_text,
        classification=classification.value if classification else None,
        category_id=_category(db, kind),
        type=transaction_type.value,
        amount=parsed.amount,
        currency=currency.value,
        date=moment,
        merchant=parsed.merchant,
        source=parsed.source.value,
        status=TransactionStatus.PENDING_REVIEW.value,
        dedupe_hash=digest,
    )


def _by_digits(db: Session, digits: str | None, currency: Currency) -> models.Account | None:
    """The account that carries these last digits in this currency, if exactly one does."""
    if not digits:
        return None
    rows = db.scalars(
        select(models.Account)
        .join(models.AccountIdentifier, models.AccountIdentifier.account_id == models.Account.id)
        .where(
            models.AccountIdentifier.digits == digits[-4:],
            models.Account.currency == currency.value,
            models.Account.archived.is_(False),
        )
        .distinct()
    ).all()
    return rows[0] if len(rows) == 1 else None


def _only_account(db: Session, types: tuple[AccountType, ...], currency: Currency) -> models.Account | None:
    """The one account of these types in this currency. With none, or several, nothing is assumed."""
    rows = db.scalars(
        select(models.Account).where(
            models.Account.type.in_([item.value for item in types]),
            models.Account.currency == currency.value,
            models.Account.archived.is_(False),
        )
    ).all()
    return rows[0] if len(rows) == 1 else None


def _own_destination(db: Session, text: str | None, currency: Currency) -> models.Account | None:
    """The user's own account a transfer is going to, when its key or its last digits say so."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("@"):
        row = db.scalars(
            select(models.Account).where(
                func.lower(models.Account.key) == text.lower(),
                models.Account.currency == currency.value,
                models.Account.archived.is_(False),
            )
        ).first()
        return row
    if text.lstrip("*").isdigit():
        return _by_digits(db, text.lstrip("*"), currency)
    return None


def _category(db: Session, kind: NotificationKind) -> uuid.UUID | None:
    name = _CATEGORY_NAMES.get(kind)
    if name is None:
        return None
    rows = db.scalars(
        select(models.Category).where(models.Category.type == "income", func.lower(models.Category.name).contains(name))
    ).all()
    return rows[0].id if len(rows) == 1 else None
