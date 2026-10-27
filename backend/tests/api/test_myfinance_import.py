import sqlite3
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models
from app.domain.entities import LOCAL_TIMEZONE
from app.importers.myfinance import ImportError_, ImportMapping, run_import
from app.importers.myfinance_backup import BackupError, read_backup
from app.services.balances import account_balances

D = Decimal
SINCE = date(2026, 9, 1)


def build_backup(path: Path, *, accounts, categories, movements, transfers, prefix: bytes = b"") -> Path:
    """Write a MyFinance-like backup with invented data. Stored balances are the sum of every movement."""
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE account (uid TEXT, title TEXT, currencyCode TEXT, isRemoved INTEGER, isActive INTEGER);
        CREATE TABLE account_balance (uid TEXT, value INTEGER);
        CREATE TABLE category (uid TEXT, title TEXT, type TEXT, isRemoved INTEGER);
        CREATE TABLE "transaction" (uid TEXT, type TEXT, amountInAccountCurrency INTEGER, date TEXT,
                                    comment TEXT, isRemoved INTEGER);
        CREATE TABLE transfer (uid TEXT, fromAmount INTEGER, fromCurrencyCode TEXT, toAmount INTEGER,
                               toCurrencyCode TEXT, date TEXT, comment TEXT, isRemoved INTEGER);
        CREATE TABLE sync_link (entityType TEXT, entityUid TEXT, otherType TEXT, otherUid TEXT, isRemoved INTEGER);
        """
    )
    balances = {title: 0 for title in accounts}
    for title in accounts:
        db.execute("INSERT INTO account VALUES (?, ?, 'COP', 0, 1)", (f"acc-{title}", title))
    for title, kind in categories.items():
        db.execute("INSERT INTO category VALUES (?, ?, ?, 0)", (f"cat-{title}", title, kind))

    for index, (account, kind, amount, day, category, removed) in enumerate(movements):
        uid = f"mov-{index}"
        db.execute(
            'INSERT INTO "transaction" VALUES (?, ?, ?, ?, ?, ?)', (uid, kind, amount * 100, day, "", int(removed))
        )
        db.execute("INSERT INTO sync_link VALUES ('Transaction', ?, 'Account', ?, 0)", (uid, f"acc-{account}"))
        if category:
            db.execute("INSERT INTO sync_link VALUES ('Transaction', ?, 'Category', ?, 0)", (uid, f"cat-{category}"))
        if not removed:
            balances[account] += amount if kind == "Income" else -amount

    for index, (origin, target, amount, day) in enumerate(transfers):
        uid = f"trf-{index}"
        db.execute("INSERT INTO transfer VALUES (?, ?, 'COP', NULL, NULL, ?, '', 0)", (uid, amount * 100, day))
        db.execute("INSERT INTO sync_link VALUES ('Transfer', ?, 'FromAccount', ?, 0)", (uid, f"acc-{origin}"))
        db.execute("INSERT INTO sync_link VALUES ('Transfer', ?, 'ToAccount', ?, 0)", (uid, f"acc-{target}"))
        balances[origin] -= amount
        balances[target] += amount

    for title, value in balances.items():
        db.execute("INSERT INTO account_balance VALUES (?, ?)", (f"acc-{title}", value * 100))

    raw = db.serialize()
    db.close()

    archive_path = path.with_suffix(".zip")
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("MyFinance.db", raw)
    # The real backups carry a few extra bytes before the zip data.
    path.write_bytes(prefix + archive_path.read_bytes())
    return path


ACCOUNTS = ["Main", "Wallet", "Cash", "Card", "Closed card", "Unused"]
CATEGORIES = {"Food": "Expense", "Paycheck": "Income", "Interest": "Income", "Fun": "Expense"}

MOVEMENTS = [
    # account, kind, amount, day, category, removed
    ("Main", "Income", 1_000_000, "2026-08-05", "Paycheck", False),  # before the window
    ("Card", "Expense", 100_000, "2026-08-20", "Food", False),  # before the window
    ("Closed card", "Expense", 50_000, "2026-08-25", "Food", False),  # before the window
    ("Main", "Income", 2_000_000, "2026-09-02", "Paycheck", False),
    ("Main", "Expense", 80_000, "2026-09-03", "Food", False),
    ("Main", "Expense", 5_000, "2026-09-04", None, False),  # no category
    ("Main", "Income", 1_234, "2026-09-05", "Interest", False),
    ("Card", "Expense", 300_000, "2026-09-06", "Fun", False),
    ("Card", "Income", 120_000, "2026-09-10", None, False),  # a payment of the card, origin unknown
    ("Wallet", "Expense", 20_000, "2026-09-11", "Paycheck", False),  # expense with an income category
    ("Cash", "Expense", 9_999, "2026-09-12", "Food", True),  # removed in the old app
    ("Closed card", "Income", 50_000, "2026-09-13", None, False),  # the closed card is paid off
]
TRANSFERS = [
    ("Main", "Cash", 200_000, "2026-09-07"),
    ("Main", "Wallet", 500_000, "2026-09-08"),
    ("Wallet", "Card", 150_000, "2026-09-09"),
    ("Main", "Cash", 1_000, "2026-08-30"),  # before the window
]

MAPPING = {
    "accounts": {
        "Main": {
            "name": "Main account",
            "type": "savings",
            "key": "@MainKey",
            "identifiers": [{"digits": "1111", "type": "account"}, {"digits": "2222", "type": "debit"}],
        },
        "Wallet": {"name": "Wallet", "type": "wallet"},
        "Cash": {"name": "Cash", "type": "cash"},
        "Card": {"name": "Card", "type": "credit_card", "identifiers": [{"digits": "3333", "type": "credit"}]},
        "Closed card": {"name": "Closed card", "type": "credit_card", "archive": True},
    },
    "categories": {"Paycheck": "Payroll", "Interest": "Yields"},
    "extra_categories": [{"name": "Card bonus", "type": "income"}],
}


@pytest.fixture
def backup_file(tmp_path):
    return build_backup(
        tmp_path / "backup.mmbackup",
        accounts=ACCOUNTS,
        categories=CATEGORIES,
        movements=MOVEMENTS,
        transfers=TRANSFERS,
        prefix=b"\x00" * 8,
    )


def mapping() -> ImportMapping:
    return ImportMapping.model_validate(MAPPING)


def account_named(db, name):
    return db.scalar(select(models.Account).where(models.Account.name == name))


def test_the_backup_reader_handles_extra_bytes_before_the_zip(backup_file):
    backup = read_backup(backup_file)

    assert {account.title for account in backup.accounts.values()} == set(ACCOUNTS)
    assert len(backup.movements) == len(MOVEMENTS) - 1  # the removed one is skipped
    assert len(backup.transfers) == len(TRANSFERS)


def test_import_ends_with_the_balances_of_the_backup(db, backup_file):
    backup = read_backup(backup_file)

    report = run_import(db, backup, mapping(), SINCE)

    assert all(expected == actual for _, expected, actual in report.balances)
    balances = account_balances(db)
    by_name = {name: balances[account_named(db, name).id] for name in ("Main account", "Wallet", "Cash", "Card")}
    stored = {account.title: account.balance for account in backup.accounts.values()}
    assert by_name == {
        "Main account": stored["Main"],
        "Wallet": stored["Wallet"],
        "Cash": stored["Cash"],
        "Card": stored["Card"],
    }


def test_accounts_open_with_the_balance_of_the_day_before(db, backup_file):
    run_import(db, read_backup(backup_file), mapping(), SINCE)

    # Main: +1,000,000 (August) - 1,000 (transfer on Aug 30) before the window.
    assert account_named(db, "Main account").initial_balance == D("999000.00")
    # Card: -100,000 (August purchase).
    assert account_named(db, "Card").initial_balance == D("-100000.00")
    assert account_named(db, "Wallet").initial_balance == D("0.00")


def test_only_accounts_with_activity_or_money_are_created(db, backup_file):
    report = run_import(db, read_backup(backup_file), mapping(), SINCE)

    assert sorted(report.accounts_created) == ["Card", "Cash", "Closed card", "Main account", "Wallet"]
    assert account_named(db, "Unused") is None


def test_key_identifiers_and_archive_come_from_the_mapping(db, backup_file):
    run_import(db, read_backup(backup_file), mapping(), SINCE)

    main = account_named(db, "Main account")
    digits = sorted(db.scalars(select(models.AccountIdentifier.digits).where(models.AccountIdentifier.account_id == main.id)))
    assert main.key == "@mainkey"
    assert digits == ["1111", "2222"]
    assert account_named(db, "Closed card").archived is True
    assert account_named(db, "Main account").archived is False


def test_card_deposits_become_payments_from_an_unknown_origin(db, backup_file):
    report = run_import(db, read_backup(backup_file), mapping(), SINCE)

    origin = db.scalar(select(models.Account).where(models.Account.type == "system"))
    assert origin.name == "Origen no identificado"
    assert report.card_payments_without_origin == 2  # the open card and the closed one

    card = account_named(db, "Card")
    payment = db.scalar(
        select(models.Transaction).where(
            models.Transaction.account_id == origin.id, models.Transaction.target_account_id == card.id
        )
    )
    assert payment.type == "transfer"
    assert payment.classification == "payment"
    assert payment.amount == D("120000.00")
    assert payment.status == "confirmed"
    assert "origen" in payment.note.lower()


def test_transfers_are_classified_by_their_destination(db, backup_file):
    run_import(db, read_backup(backup_file), mapping(), SINCE)

    card, cash = account_named(db, "Card"), account_named(db, "Cash")
    to_card = db.scalar(
        select(models.Transaction).where(
            models.Transaction.source_id == "trf-2", models.Transaction.target_account_id == card.id
        )
    )
    to_cash = db.scalar(select(models.Transaction).where(models.Transaction.source_id == "trf-0"))
    assert to_card.classification == "payment"
    assert to_cash.classification == "own_transfer"
    assert to_cash.target_account_id == cash.id


def test_categories_are_renamed_created_once_and_must_match_the_movement_type(db, backup_file):
    report = run_import(db, read_backup(backup_file), mapping(), SINCE)

    names = {(c.name, c.type) for c in db.scalars(select(models.Category))}
    assert {("Payroll", "income"), ("Yields", "income"), ("Food", "expense"), ("Fun", "expense"),
            ("Card bonus", "income")} <= names
    assert ("Paycheck", "income") not in names
    # The wallet expense used an income category: imported without category, with a warning.
    mismatched = db.scalar(select(models.Transaction).where(models.Transaction.source_id == "mov-9"))
    assert mismatched.category_id is None
    assert report.warnings


def test_removed_movements_and_movements_before_the_window_are_left_out(db, backup_file):
    report = run_import(db, read_backup(backup_file), mapping(), SINCE)

    imported = set(db.scalars(select(models.Transaction.source_id).where(models.Transaction.source == "myfinance_import")))
    assert "mov-10" not in imported  # removed
    assert not imported & {"mov-0", "mov-1", "mov-2", "trf-3"}  # before the cutoff
    assert report.movements_imported == 8
    assert report.transfers_imported == 3


def test_imported_movements_are_confirmed_and_dated_at_noon_colombian_time(db, backup_file):
    run_import(db, read_backup(backup_file), mapping(), SINCE)

    row = db.scalar(select(models.Transaction).where(models.Transaction.source_id == "mov-3"))
    assert row.status == "confirmed"
    assert row.source == "myfinance_import"
    local = row.date.astimezone(LOCAL_TIMEZONE)
    assert (local.date(), local.hour) == (date(2026, 9, 2), 12)


def test_everything_is_saved_not_only_the_accounts(connection, backup_file):
    # The command line closes its session right after the import. Whatever was not committed by
    # then is rolled back, so the check has to happen after closing, with another session.
    with Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as importing:
        run_import(importing, read_backup(backup_file), mapping(), SINCE)

    with Session(bind=connection, join_transaction_mode="create_savepoint") as fresh:
        imported = fresh.scalar(
            select(func.count()).select_from(models.Transaction).where(models.Transaction.source == "myfinance_import")
        )
        categories = fresh.scalar(select(func.count()).select_from(models.Category))
        origin = fresh.scalar(select(models.Account).where(models.Account.type == "system"))
        archived = fresh.scalar(select(models.Account.archived).where(models.Account.name == "Closed card"))

    assert imported == 11  # 8 movements, 3 transfers
    assert categories >= 5
    assert origin is not None
    assert archived is True


def test_marked_movements_are_imported_as_balance_adjustments(db, backup_file):
    marked = ImportMapping.model_validate({**MAPPING, "adjustment_movements": ["mov-3", "mov-4"]})

    report = run_import(db, read_backup(backup_file), marked, SINCE)

    assert report.adjustments_imported == 2
    income_correction = db.scalar(select(models.Transaction).where(models.Transaction.source_id == "mov-3"))
    expense_correction = db.scalar(select(models.Transaction).where(models.Transaction.source_id == "mov-4"))
    assert (income_correction.type, income_correction.amount) == ("adjustment_in", D("2000000.00"))
    assert (expense_correction.type, expense_correction.amount) == ("adjustment_out", D("80000.00"))
    assert income_correction.category_id is None and expense_correction.category_id is None
    assert income_correction.note and expense_correction.note
    # An adjustment moves the balance exactly like the movement it replaces.
    assert all(expected == actual for _, expected, actual in report.balances)


def test_running_the_import_twice_changes_nothing(db, backup_file):
    backup = read_backup(backup_file)
    run_import(db, backup, mapping(), SINCE)
    count = len(list(db.scalars(select(models.Transaction.id))))

    second = run_import(db, backup, mapping(), SINCE)

    assert second.movements_imported == 0 and second.transfers_imported == 0
    assert second.movements_skipped == 8 and second.transfers_skipped == 3
    assert second.accounts_created == []
    assert len(list(db.scalars(select(models.Transaction.id)))) == count


def test_an_account_without_mapping_stops_the_import(db, backup_file):
    incomplete = ImportMapping.model_validate(
        {**MAPPING, "accounts": {k: v for k, v in MAPPING["accounts"].items() if k != "Wallet"}}
    )

    with pytest.raises(ImportError_, match="Wallet"):
        run_import(db, read_backup(backup_file), incomplete, SINCE)


def test_balances_that_do_not_match_stop_the_import(db, backup_file):
    # An account with the same name and extra money already exists: the result cannot match the backup.
    db.add(models.Account(name="Cash", type="cash", currency="COP", initial_balance=D("777"), archived=False))
    db.commit()

    with pytest.raises(ImportError_, match="Cash"):
        run_import(db, read_backup(backup_file), mapping(), SINCE)


def test_a_file_that_is_not_a_backup_is_rejected(tmp_path):
    not_a_backup = tmp_path / "notes.mmbackup"
    not_a_backup.write_bytes(b"this is not a zip file")

    with pytest.raises(BackupError):
        read_backup(not_a_backup)


def test_a_backup_whose_balances_do_not_add_up_is_rejected(tmp_path):
    path = build_backup(tmp_path / "x.mmbackup", accounts=["A"], categories={}, movements=[("A", "Income", 10, "2026-09-02", None, False)], transfers=[])
    db = sqlite3.connect(":memory:")
    with zipfile.ZipFile(path.with_suffix(".zip")) as archive:
        db.deserialize(archive.read("MyFinance.db"))
    db.execute("UPDATE account_balance SET value = value + 100")
    db.commit()
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(tampered, "w") as archive:
        archive.writestr("MyFinance.db", db.serialize())

    with pytest.raises(BackupError, match="balances"):
        read_backup(tampered)
