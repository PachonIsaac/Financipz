import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MONEY = Numeric(14, 2)
UUID_PK = UUID(as_uuid=True)


def in_list(column: str, values: tuple[str, ...]) -> str:
    """Build a SQL check expression that restricts a column to a fixed set of values."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


ACCOUNT_TYPES = ("cash", "bank", "credit_card", "savings", "wallet", "exchange", "loan", "system")
CURRENCIES = ("COP", "USD")
# The TRM is only stored for foreign currencies: COP is the base currency.
FX_CURRENCIES = ("USD",)
CATEGORY_TYPES = ("expense", "income", "transfer")
TRANSACTION_TYPES = ("expense", "income", "transfer", "adjustment_in", "adjustment_out")
CLASSIFICATIONS = ("loan", "expense", "payment", "own_transfer")
TRANSACTION_SOURCES = ("manual", "gmail", "sms_uala", "wallet", "binance", "myfinance_import")
TRANSACTION_STATUSES = ("pending_review", "confirmed", "discarded")
IDENTIFIER_TYPES = ("account", "debit", "credit")
INTEGRATION_PROVIDERS = ("gmail", "binance")
INTEGRATION_STATUSES = ("active", "error", "disconnected")
PROCESSED_EMAIL_RESULTS = ("ok", "unrecognized", "error", "ignored")
CRYPTO_SIDES = ("buy", "sell")


class Account(Base):
    """A place where money lives or is owed. Accounts are archived, never deleted."""

    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(in_list("type", ACCOUNT_TYPES), name="type"),
        CheckConstraint(in_list("currency", CURRENCIES), name="currency"),
        CheckConstraint("key IS NULL OR key = lower(key)", name="key_lowercase"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    # Only used for loan accounts: the person the money was lent to.
    counterparty: Mapped[str | None] = mapped_column(Text)
    # Optional Bre-b key. Lowercase, unique when present.
    key: Mapped[str | None] = mapped_column(Text, unique=True)
    currency: Mapped[str] = mapped_column(String(3))
    # Balances may be negative (for example, a credit card whose debt exceeds payments).
    initial_balance: Mapped[Decimal] = mapped_column(MONEY, server_default=text("0"))
    archived: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class AccountIdentifier(Base):
    __tablename__ = "account_identifiers"
    __table_args__ = (
        CheckConstraint(in_list("type", IDENTIFIER_TYPES), name="type"),
        CheckConstraint("digits ~ '^[0-9]{4}$'", name="digits_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    digits: Mapped[str] = mapped_column(String(4))
    type: Mapped[str] = mapped_column(Text)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(in_list("type", CATEGORY_TYPES), name="type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(Text)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        # Amounts are always positive. The sign comes from `type`.
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(in_list("type", TRANSACTION_TYPES), name="type"),
        CheckConstraint(in_list("currency", CURRENCIES), name="currency"),
        CheckConstraint(in_list("source", TRANSACTION_SOURCES), name="source"),
        CheckConstraint(in_list("status", TRANSACTION_STATUSES), name="status"),
        CheckConstraint(
            "classification IS NULL OR " + in_list("classification", CLASSIFICATIONS),
            name="classification",
        ),
        # Only transfers have a destination account, and it cannot be the source account.
        CheckConstraint(
            "target_account_id IS NULL OR type = 'transfer'",
            name="target_only_on_transfer",
        ),
        CheckConstraint(
            "target_account_id IS NULL OR target_account_id <> account_id",
            name="target_differs_from_source",
        ),
        # Only transfers are classified, and a loan needs the loan account that receives it.
        CheckConstraint(
            "classification IS NULL OR type = 'transfer'",
            name="classification_only_on_transfer",
        ),
        CheckConstraint(
            "classification IS DISTINCT FROM 'loan' OR target_account_id IS NOT NULL",
            name="loan_requires_target",
        ),
        # Cross-currency transfers carry the amount received and the TRM used, together.
        CheckConstraint("(target_amount IS NULL) = (fx_rate IS NULL)", name="fx_pair_complete"),
        CheckConstraint("target_amount IS NULL OR type = 'transfer'", name="fx_only_on_transfer"),
        CheckConstraint(
            "(target_amount IS NULL OR target_amount > 0) AND (fx_rate IS NULL OR fx_rate > 0)",
            name="fx_positive",
        ),
        # Manual balance adjustments must explain why they happened.
        CheckConstraint(
            "type NOT IN ('adjustment_in', 'adjustment_out') OR (note IS NOT NULL AND btrim(note) <> '')",
            name="adjustment_requires_note",
        ),
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_account_id_date", "account_id", "date"),
        Index(
            "ix_transactions_pending_review",
            "date",
            postgresql_where=text("status = 'pending_review'"),
        ),
        # Makes imports idempotent: the same record in the same source is stored once.
        Index(
            "uq_transactions_source_source_id",
            "source",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    target_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    target_text: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    type: Mapped[str] = mapped_column(Text)
    # Always in the currency of the source account.
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    # Amount received by the target account, in its own currency. Only when the currencies differ.
    target_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    # TRM of the day used for the conversion. Stored so the movement does not change if rates are corrected.
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    merchant: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    # ID of the record in the source system (for example, the MyFinance row), when there is one.
    source_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'confirmed'"))
    # Null for manual entries. Unique when present, so repeated notifications are not stored twice.
    dedupe_hash: Mapped[str | None] = mapped_column(Text, unique=True)
    external_reference: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    # Text contained in the merchant name.
    pattern: Mapped[str] = mapped_column(Text)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("category_id", "month", name="uq_budgets_category_id_month"),
        CheckConstraint("limit_amount > 0", name="limit_positive"),
        CheckConstraint("EXTRACT(DAY FROM month) = 1", name="month_first_day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    # First day of the month.
    month: Mapped[dt.date] = mapped_column(Date)
    limit_amount: Mapped[Decimal] = mapped_column(MONEY)


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (
        CheckConstraint(in_list("provider", INTEGRATION_PROVIDERS), name="provider"),
        CheckConstraint(in_list("status", INTEGRATION_STATUSES), name="status"),
        # One connection per provider.
        Index("uq_integrations_provider", "provider", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    provider: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    # Encrypted with a key that lives in the backend environment, never in the database.
    encrypted_secret: Mapped[bytes | None] = mapped_column(LargeBinary)
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Notices about the connection ({"code", "message"} objects): what the user should know, or why it failed.
    warnings: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class ProcessedEmail(Base):
    __tablename__ = "processed_emails"
    __table_args__ = (
        CheckConstraint(
            "result IS NULL OR " + in_list("result", PROCESSED_EMAIL_RESULTS),
            name="result",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"))
    message_id: Mapped[str] = mapped_column(Text, unique=True)
    sender: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str | None] = mapped_column(Text)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"))


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (
        CheckConstraint(in_list("currency", FX_CURRENCIES), name="currency"),
        CheckConstraint("value > 0", name="value_positive"),
    )

    # One row per day and currency.
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    source: Mapped[str] = mapped_column(Text)


class CryptoBalance(Base):
    __tablename__ = "crypto_balances"
    __table_args__ = (
        # A day without a sync produces no row, so "no data" is different from "zero".
        UniqueConstraint("account_id", "asset", "date", name="uq_crypto_balances_account_id_asset_date"),
        CheckConstraint("quantity >= 0 AND value_usd >= 0", name="non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    asset: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    # Null when the asset could not be priced: "unknown" is different from "worth zero".
    value_usd: Mapped[Decimal | None] = mapped_column(MONEY)
    date: Mapped[dt.date] = mapped_column(Date)


class CryptoTrade(Base):
    __tablename__ = "crypto_trades"
    __table_args__ = (
        CheckConstraint(in_list("side", CRYPTO_SIDES), name="side"),
        CheckConstraint("quantity >= 0 AND price > 0 AND fee >= 0", name="non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, server_default=func.gen_random_uuid())
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    pair: Mapped[str] = mapped_column(Text)
    side: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    price: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    fee: Mapped[Decimal] = mapped_column(Numeric(30, 12), server_default=text("0"))
    fee_asset: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    external_id: Mapped[str] = mapped_column(Text, unique=True)
