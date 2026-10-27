"""Reader for MyFinance backups: a zip file that holds a SQLite database.

The backup is untrusted input. Only the database member is read, from memory, and nothing from
the archive is written to disk.
"""

import sqlite3
import zipfile
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

DATABASE_MEMBER = "MyFinance.db"
MAX_DATABASE_BYTES = 200 * 1024 * 1024
# The SQLite progress handler runs every 1000 virtual machine instructions. Reading a real backup
# takes a tiny fraction of this; a hostile file that makes a query loop is stopped by it.
PROGRESS_INTERVAL = 1000
MAX_PROGRESS_CALLS = 50_000
MOVEMENT_KINDS = {"expense", "income"}


class BackupError(ValueError):
    """The backup cannot be read, or it does not add up."""


@dataclass(frozen=True)
class BackupAccount:
    uid: str
    title: str
    currency: str
    balance: Decimal
    removed: bool
    active: bool


@dataclass(frozen=True)
class BackupCategory:
    uid: str
    title: str
    type: str  # "expense" or "income"


@dataclass(frozen=True)
class BackupMovement:
    uid: str
    kind: str  # "expense" or "income"
    account_uid: str
    category_uid: str | None
    amount: Decimal
    day: date
    note: str


@dataclass(frozen=True)
class BackupTransfer:
    uid: str
    from_uid: str
    to_uid: str
    amount_out: Decimal
    amount_in: Decimal
    day: date
    note: str


@dataclass
class Backup:
    accounts: dict[str, BackupAccount] = field(default_factory=dict)
    categories: dict[str, BackupCategory] = field(default_factory=dict)
    movements: list[BackupMovement] = field(default_factory=list)
    transfers: list[BackupTransfer] = field(default_factory=list)

    def effects(self, since: date | None = None, exclude: frozenset[str] | set[str] = frozenset()) -> dict[str, Decimal]:
        """Signed effect of the movements on each account, from `since` on (everything if None).

        Movements whose id is in `exclude` are left out of the sum.
        """
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for movement in self.movements:
            if movement.uid in exclude:
                continue
            if since is None or movement.day >= since:
                sign = 1 if movement.kind == "income" else -1
                totals[movement.account_uid] += sign * movement.amount
        for transfer in self.transfers:
            if since is None or transfer.day >= since:
                totals[transfer.from_uid] -= transfer.amount_out
                totals[transfer.to_uid] += transfer.amount_in
        return totals


def read_backup(path: Path) -> Backup:
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(_read_database(path))
        _limit_work(connection)
        _check_schema(connection)
        backup = _load(connection)
    except BackupError:
        raise
    except (sqlite3.Error, ValueError, KeyError, TypeError, AttributeError, ArithmeticError) as error:
        # Only the kind of failure is reported, never the content of the (private) backup.
        raise BackupError(f"The backup cannot be read ({type(error).__name__})") from error
    finally:
        connection.close()
    _check_links(backup)
    _check_balances(backup)
    return backup


def _limit_work(connection: sqlite3.Connection) -> None:
    calls = 0

    def stop_when_too_long() -> int:
        nonlocal calls
        calls += 1
        return 1 if calls > MAX_PROGRESS_CALLS else 0

    connection.set_progress_handler(stop_when_too_long, PROGRESS_INTERVAL)


def _check_schema(connection: sqlite3.Connection) -> None:
    """A MyFinance database only has tables and indexes. Views or triggers are not expected."""
    unexpected = connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type NOT IN ('table', 'index')"
    ).fetchone()[0]
    if unexpected:
        raise BackupError("The backup database has objects that a MyFinance backup does not have")


def _read_database(path: Path) -> bytes:
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(DATABASE_MEMBER)
            if info.file_size > MAX_DATABASE_BYTES:
                raise BackupError("The backup database is unexpectedly large")
            return archive.read(info)
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError, NotImplementedError, EOFError, zlib.error) as error:
        raise BackupError(f"{path.name} is not a readable MyFinance backup ({type(error).__name__})") from error


def _cents(value: int) -> Decimal:
    return Decimal(value) / 100


def _links(connection: sqlite3.Connection, entity: str, other: str) -> dict[str, str]:
    rows = connection.execute(
        "SELECT entityUid, otherUid FROM sync_link WHERE entityType = ? AND otherType = ? AND isRemoved = 0",
        (entity, other),
    )
    return dict(rows.fetchall())


def _load(connection: sqlite3.Connection) -> Backup:
    backup = Backup()

    balances = dict(connection.execute("SELECT uid, value FROM account_balance"))
    for uid, title, currency, removed, active in connection.execute(
        "SELECT uid, title, currencyCode, isRemoved, isActive FROM account"
    ):
        backup.accounts[uid] = BackupAccount(
            uid=uid,
            title=title,
            currency=currency,
            balance=_cents(balances.get(uid, 0)),
            removed=bool(removed),
            active=bool(active),
        )

    for uid, title, kind in connection.execute("SELECT uid, title, type FROM category WHERE isRemoved = 0"):
        backup.categories[uid] = BackupCategory(uid=uid, title=title, type=kind.lower())

    movement_account = _links(connection, "Transaction", "Account")
    movement_category = _links(connection, "Transaction", "Category")
    for uid, kind, amount, day, note in connection.execute(
        'SELECT uid, type, amountInAccountCurrency, date, comment FROM "transaction" WHERE isRemoved = 0'
    ):
        if uid not in movement_account:
            raise BackupError("A movement has no account")
        if kind is None or kind.lower() not in MOVEMENT_KINDS:
            raise BackupError("A movement has an unknown type")
        backup.movements.append(
            BackupMovement(
                uid=uid,
                kind=kind.lower(),
                account_uid=movement_account[uid],
                category_uid=movement_category.get(uid),
                amount=_cents(amount),
                day=date.fromisoformat(day[:10]),
                note=(note or "").strip(),
            )
        )

    from_account = _links(connection, "Transfer", "FromAccount")
    to_account = _links(connection, "Transfer", "ToAccount")
    for uid, amount_out, currency_out, amount_in, currency_in, day, note in connection.execute(
        "SELECT uid, fromAmount, fromCurrencyCode, toAmount, toCurrencyCode, date, comment"
        " FROM transfer WHERE isRemoved = 0"
    ):
        if uid not in from_account or uid not in to_account:
            raise BackupError("A transfer is missing one of its accounts")
        # An empty received amount means the same as the amount sent (same currency).
        if amount_in is not None and (amount_in != amount_out or currency_in not in (None, currency_out)):
            raise BackupError("Transfers between different currencies are not supported")
        backup.transfers.append(
            BackupTransfer(
                uid=uid,
                from_uid=from_account[uid],
                to_uid=to_account[uid],
                amount_out=_cents(amount_out),
                amount_in=_cents(amount_out),
                day=date.fromisoformat(day[:10]),
                note=(note or "").strip(),
            )
        )
    return backup


def _check_links(backup: Backup) -> None:
    """Every movement and transfer must belong to accounts that are in the backup."""
    known = backup.accounts.keys()
    if any(m.account_uid not in known for m in backup.movements) or any(
        t.from_uid not in known or t.to_uid not in known for t in backup.transfers
    ):
        raise BackupError("A movement refers to an account that is not in the backup")


def _check_balances(backup: Backup) -> None:
    """The sum of every movement must equal each account's stored balance. If it does not, this
    reader does not understand the file, and importing from it would give wrong balances."""
    effects = backup.effects()
    wrong = [
        account.title
        for account in backup.accounts.values()
        if effects.get(account.uid, Decimal(0)) != account.balance
    ]
    if wrong:
        raise BackupError(f"Stored balances do not match the movements of {len(wrong)} account(s)")
