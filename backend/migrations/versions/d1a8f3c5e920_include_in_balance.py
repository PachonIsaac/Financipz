"""let the user leave an account out of the balance

Revision ID: d1a8f3c5e920
Revises: cbb0b0f8a19c
Create Date: 2026-10-28 10:00:00.000000

Every account counts by default, as before. The column is added with a default, so the code that is
already running keeps working until it learns about it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1a8f3c5e920"
down_revision: Union[str, Sequence[str], None] = "cbb0b0f8a19c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("include_in_balance", sa.Boolean(), server_default=sa.text("true"), nullable=False))


def downgrade() -> None:
    op.drop_column("accounts", "include_in_balance")
