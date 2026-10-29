"""remove the token table of the iOS shortcut, which is no longer used

Revision ID: g3d8b5f7c924
Revises: f2c9a4e6b813
Create Date: 2026-10-29 10:00:00.000000

The shortcut that sent SMS to the API was dropped. Its token table held only hashes of tokens that no longer open
anything.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "g3d8b5f7c924"
down_revision: Union[str, Sequence[str], None] = "f2c9a4e6b813"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("ingest_tokens")


def downgrade() -> None:
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
