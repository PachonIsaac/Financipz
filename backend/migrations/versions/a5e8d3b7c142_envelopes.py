"""envelopes: money set apart inside an account

Revision ID: a5e8d3b7c142
Revises: f2c9a4e6b813
Create Date: 2026-11-07 12:00:00.000000

Two tables that follow the rule of every other one: row level security on and no access for the roles
of the database REST layer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a5e8d3b7c142"
down_revision: Union[str, Sequence[str], None] = "f2c9a4e6b813"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "envelopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("target_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("repeats_yearly", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("target_amount IS NULL OR target_amount > 0", name=op.f("ck_envelopes_target_positive")),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name=op.f("fk_envelopes_account_id_accounts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_envelopes")),
    )
    op.create_table(
        "envelope_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("envelope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_envelope_entries_amount_not_zero")),
        sa.ForeignKeyConstraint(
            ["envelope_id"], ["envelopes.id"], name=op.f("fk_envelope_entries_envelope_id_envelopes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_envelope_entries_transaction_id_transactions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_envelope_entries")),
    )
    op.create_index("ix_envelope_entries_envelope_id", "envelope_entries", ["envelope_id"])
    op.execute('ALTER TABLE "envelopes" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "envelope_entries" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("envelope_entries")
    op.drop_table("envelopes")
