"""Import the recent movements of a MyFinance backup.

Only the days from `since` on are imported. Each account opens with the balance it had the day
before, so that after the import every balance equals the one stored in the backup. If any
balance does not match, nothing is saved.

Which backup account becomes which account here is decided by a private mapping file, so no
real names, numbers or keys live in the code.

    python -m app.importers.myfinance --backup FILE --mapping FILE --since 2026-09-01          # simulation
    python -m app.importers.myfinance --backup FILE --mapping FILE --since 2026-09-01 --apply  # saves
"""

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db import models
from app.db.session import get_engine
from app.domain.entities import LOCAL_TIMEZONE, AccountType
from app.importers.myfinance_backup import Backup, BackupAccount, BackupError, read_backup
from app.schemas.accounts import AccountCreate, IdentifierIn
from app.services.accounts import create_account, replace_identifiers
from app.services.balances import account_balances

SOURCE = "myfinance_import"
ADJUSTMENT_NOTE = "Ajuste de saldo importado"


class ImportError_(Exception):
    """The import cannot continue, and nothing was saved."""


class AccountMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: AccountType
    key: str | None = None
    identifiers: list[IdentifierIn] = []
    # Archive the account once imported (for example, a card that was paid off and closed).
    archive: bool = False


class ImportMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Account title in the backup -> account here.
    accounts: dict[str, AccountMapping]
    # Category title in the backup -> name here, for the ones that are renamed.
    categories: dict[str, str] = {}
    # Categories to create even if no imported movement uses them.
    extra_categories: list[dict[str, str]] = []
    # Ids of backup movements that were manual balance corrections. They are imported as balance
    # adjustments, which do not count in the cash flow.
    adjustment_movements: list[str] = []
    # Ids of backup movements that are not imported at all: their effect is folded into the opening
    # balance of their account, so the final balance still equals the backup's without leaving a
    # movement behind. For corrections that only made sense in the old app.
    absorbed_movements: list[str] = []


@dataclass
class ImportReport:
    accounts_created: list[str] = field(default_factory=list)
    accounts_reused: list[str] = field(default_factory=list)
    categories_created: int = 0
    movements_imported: int = 0
    movements_skipped: int = 0
    movements_absorbed: int = 0
    adjustments_imported: int = 0
    transfers_imported: int = 0
    transfers_skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    balances: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)


def load_mapping(path: Path) -> ImportMapping:
    try:
        return ImportMapping.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except ValidationError as error:
        # Where the problem is and what kind, never the values: the file holds personal data.
        problems = "; ".join(f"{'.'.join(str(part) for part in e['loc'])}: {e['type']}" for e in error.errors())
        raise ImportError_(f"The mapping file is not valid ({problems})") from error
    except (OSError, ValueError) as error:
        raise ImportError_(f"The mapping file cannot be read ({type(error).__name__})") from error


def run_import(db: Session, backup: Backup, mapping: ImportMapping, since: date) -> ImportReport:
    """Import into `db` and commit the session's work.

    If the balances do not match the backup, `ImportError_` is raised before anything is committed
    by this function. The caller owns the outer transaction and decides whether to keep it.
    """
    # Accounts are created through services that commit as they go. Inside a savepoint those commits
    # can be undone as a whole if the balances do not match; on a plain session they could not.
    # (The connection tells whether a savepoint is active; the session's own flag does not.)
    if not db.connection().in_nested_transaction():
        raise ImportError_("The import must run in a session inside a savepoint, so it can be undone as a whole")

    report = ImportReport()
    absorbed_ids = frozenset(mapping.absorbed_movements)
    adjustment_ids = set(mapping.adjustment_movements)
    effects = backup.effects(since, exclude=absorbed_ids)

    in_window = {m.account_uid for m in backup.movements if m.day >= since}
    in_window |= {t.from_uid for t in backup.transfers if t.day >= since}
    in_window |= {t.to_uid for t in backup.transfers if t.day >= since}
    included = [
        account
        for account in backup.accounts.values()
        if account.uid in in_window or account.balance != 0
    ]

    missing = sorted(account.title for account in included if account.title not in mapping.accounts)
    if missing:
        raise ImportError_(f"These backup accounts have no mapping: {', '.join(missing)}")

    _refuse_undecided_card_deposits(backup, mapping, since, absorbed_ids, adjustment_ids)

    rows = {account.uid: _ensure_account(db, account, mapping, effects, report) for account in included}
    types = {uid: AccountType(row.type) for uid, row in rows.items()}

    categories = _CategoryResolver(db, backup, mapping, report)
    imported = set(db.scalars(select(models.Transaction.source_id).where(models.Transaction.source == SOURCE)))

    for movement in sorted((m for m in backup.movements if m.day >= since), key=lambda m: m.day):
        if movement.uid in absorbed_ids:
            if movement.uid in imported:
                raise ImportError_("A movement marked as absorbed was already imported: remove it first")
            report.movements_absorbed += 1
            continue
        if movement.uid in imported:
            report.movements_skipped += 1
            continue

        account = rows[movement.account_uid]
        category = categories.resolve(movement.category_uid, movement.kind, report)
        common = {
            "id": uuid.uuid4(),
            "amount": movement.amount,
            "currency": account.currency,
            "date": _noon(movement.day),
            "source": SOURCE,
            "source_id": movement.uid,
            "status": "confirmed",
        }

        if movement.uid in adjustment_ids:
            db.add(
                models.Transaction(
                    **common,
                    account_id=account.id,
                    type="adjustment_in" if movement.kind == "income" else "adjustment_out",
                    note=_join_notes(ADJUSTMENT_NOTE, movement.note),
                )
            )
            report.adjustments_imported += 1
        else:
            db.add(
                models.Transaction(
                    **common,
                    account_id=account.id,
                    type=movement.kind,
                    category_id=category,
                    note=movement.note or None,
                )
            )
        report.movements_imported += 1

    for transfer in sorted((t for t in backup.transfers if t.day >= since), key=lambda t: t.day):
        if transfer.uid in imported:
            report.transfers_skipped += 1
            continue
        source, target = rows[transfer.from_uid], rows[transfer.to_uid]
        db.add(
            models.Transaction(
                id=uuid.uuid4(),
                account_id=source.id,
                target_account_id=target.id,
                type="transfer",
                classification=_classify(types[transfer.from_uid], types[transfer.to_uid]),
                amount=transfer.amount_out,
                currency=source.currency,
                date=_noon(transfer.day),
                note=transfer.note or None,
                source=SOURCE,
                source_id=transfer.uid,
                status="confirmed",
            )
        )
        report.transfers_imported += 1

    db.flush()
    _reconcile(db, backup, included, rows, report)

    for account in included:
        if mapping.accounts[account.title].archive:
            rows[account.uid].archived = True
    # Everything above is one unit: commit it here, so closing the session cannot silently undo the
    # part that came after the accounts were created. The caller still decides whether the outer
    # transaction is kept or rolled back.
    db.commit()
    return report


def _ensure_account(
    db: Session,
    account: BackupAccount,
    mapping: ImportMapping,
    effects: dict[str, Decimal],
    report: ImportReport,
) -> models.Account:
    wanted = mapping.accounts[account.title]
    existing = db.scalar(select(models.Account).where(models.Account.name == wanted.name))
    if existing is not None:
        report.accounts_reused.append(wanted.name)
        return existing

    opening = account.balance - effects.get(account.uid, Decimal(0))
    try:
        created = create_account(
            db,
            AccountCreate(
                name=wanted.name,
                type=wanted.type,
                currency=account.currency,
                initial_balance=opening,
                key=wanted.key,
            ),
        )
        if wanted.identifiers:
            replace_identifiers(db, created.id, wanted.identifiers)
    except ApiError as error:
        raise ImportError_(f"Cannot create account '{wanted.name}': {error.message}") from error
    except ValidationError as error:
        fields = ", ".join(sorted({str(e["loc"][0]) for e in error.errors()}))
        raise ImportError_(f"Cannot create account '{wanted.name}': invalid {fields}") from error
    report.accounts_created.append(wanted.name)
    return db.get(models.Account, created.id)


def _refuse_undecided_card_deposits(
    backup: Backup,
    mapping: ImportMapping,
    since: date,
    absorbed_ids: frozenset[str],
    adjustment_ids: set[str],
) -> None:
    """A deposit on a credit card has no source account in the backup, so it cannot become a payment.

    It has to be decided in the mapping: a balance adjustment, or absorbed into the opening balance.
    Guessing an origin would invent an account that is always in the red.
    """
    undecided = 0
    for movement in backup.movements:
        if movement.day < since or movement.kind != "income" or movement.uid in absorbed_ids | adjustment_ids:
            continue
        mapped = mapping.accounts.get(backup.accounts[movement.account_uid].title)
        if mapped is not None and mapped.type is AccountType.CREDIT_CARD:
            undecided += 1
    if undecided:
        raise ImportError_(
            f"{undecided} deposit(s) into credit cards have no known origin: list their ids under "
            "adjustment_movements or absorbed_movements in the mapping"
        )


class _CategoryResolver:
    """Finds or creates the category for each backup category, once."""

    def __init__(self, db: Session, backup: Backup, mapping: ImportMapping, report: ImportReport) -> None:
        self._db = db
        self._backup = backup
        self._mapping = mapping
        self._cache: dict[str, uuid.UUID] = {}
        for extra in mapping.extra_categories:
            self._get_or_create(extra["name"], extra["type"], report)

    def resolve(self, backup_uid: str | None, movement_kind: str, report: ImportReport) -> uuid.UUID | None:
        if backup_uid is None or backup_uid not in self._backup.categories:
            return None
        category = self._backup.categories[backup_uid]
        if category.type != movement_kind:
            report.warnings.append("A movement was imported without category because its type did not match")
            return None
        name = self._mapping.categories.get(category.title, category.title)
        return self._get_or_create(name, category.type, report)

    def _get_or_create(self, name: str, category_type: str, report: ImportReport) -> uuid.UUID:
        cache_key = f"{category_type}:{name.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        existing = self._db.scalar(
            select(models.Category.id).where(
                func.lower(models.Category.name) == name.lower(),
                models.Category.type == category_type,
                models.Category.parent_id.is_(None),
            )
        )
        if existing is None:
            existing = uuid.uuid4()
            self._db.add(models.Category(id=existing, name=name, type=category_type))
            self._db.flush()
            report.categories_created += 1
        self._cache[cache_key] = existing
        return existing


def _classify(source: AccountType, target: AccountType) -> str:
    if AccountType.LOAN in (source, target):
        return "loan"
    if target is AccountType.CREDIT_CARD:
        return "payment"
    return "own_transfer"


def _reconcile(
    db: Session,
    backup: Backup,
    included: list[BackupAccount],
    rows: dict[str, models.Account],
    report: ImportReport,
) -> None:
    """Every imported account must end with the balance the backup has for it."""
    balances = account_balances(db)
    mismatches = []
    for account in included:
        actual = balances[rows[account.uid].id]
        report.balances.append((rows[account.uid].name, account.balance, actual))
        if actual != account.balance:
            mismatches.append(rows[account.uid].name)
    if mismatches:
        raise ImportError_(f"Balances do not match the backup for: {', '.join(mismatches)}")


def _noon(day: date) -> datetime:
    # The backup only has the day. Noon keeps it on that day in any timezone near Colombia.
    return datetime.combine(day, time(12, 0), tzinfo=LOCAL_TIMEZONE)


def _join_notes(*notes: str) -> str:
    return ". ".join(note for note in notes if note)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import recent movements from a MyFinance backup.")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--since", type=date.fromisoformat, required=True, help="first day to import, YYYY-MM-DD")
    parser.add_argument("--apply", action="store_true", help="save the import (without it, nothing is saved)")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2

    try:
        mapping = load_mapping(args.mapping)
        backup = read_backup(args.backup)
    except (ImportError_, BackupError) as error:
        print(f"Cannot start: {error}", file=sys.stderr)
        return 2

    with get_engine(settings.database_url).connect() as connection:
        outer = connection.begin()
        # Services commit as they go; with a savepoint those commits can still be undone as a whole.
        with Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
            try:
                report = run_import(db, backup, mapping, args.since)
            except ImportError_ as error:
                outer.rollback()
                print(f"Nothing was saved: {error}", file=sys.stderr)
                return 1

        _print_report(report, applied=args.apply)
        if args.apply:
            outer.commit()
        else:
            outer.rollback()
    return 0


def _print_report(report: ImportReport, applied: bool) -> None:
    print("SAVED" if applied else "SIMULATION (nothing was saved; use --apply to save)")
    print(f"accounts created: {len(report.accounts_created)}, reused: {len(report.accounts_reused)}")
    print(f"categories created: {report.categories_created}")
    print(f"movements imported: {report.movements_imported}, already there: {report.movements_skipped}")
    print(f"movements absorbed into opening balances: {report.movements_absorbed}")
    print(f"balance adjustments: {report.adjustments_imported}")
    print(f"transfers imported: {report.transfers_imported}, already there: {report.transfers_skipped}")
    for warning in sorted(set(report.warnings)):
        print(f"warning: {warning} (x{report.warnings.count(warning)})")
    print("balances (account | backup | here):")
    for name, expected, actual in report.balances:
        print(f"  {name} | {expected:,.2f} | {actual:,.2f} | {'OK' if expected == actual else 'DIFFERENT'}")


if __name__ == "__main__":
    raise SystemExit(main())
