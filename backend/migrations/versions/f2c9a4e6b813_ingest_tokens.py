"""a token for the iOS shortcut that sends notifications

Revision ID: f2c9a4e6b813
Revises: e4b7c2d9a1f6
Create Date: 2026-10-28 20:00:00.000000

Only the hash of the token is stored. The table follows the rule of every other one: row level security on,
and no access for the roles of the database REST layer (the default privileges were already revoked).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2c9a4e6b813"
down_revision: Union[str, Sequence[str], None] = "e4b7c2d9a1f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_ingest_tokens_token_hash")),
    )
    op.execute('ALTER TABLE "ingest_tokens" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("ingest_tokens")
