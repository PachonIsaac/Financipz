"""store connection notices and allow unpriced crypto balances

Revision ID: b3f1c2a47d10
Revises: 914d96196da1
Create Date: 2026-10-27 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3f1c2a47d10'
down_revision: Union[str, Sequence[str], None] = '914d96196da1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'integrations',
        sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.alter_column('crypto_balances', 'value_usd', existing_type=sa.NUMERIC(precision=14, scale=2), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE crypto_balances SET value_usd = 0 WHERE value_usd IS NULL")
    op.alter_column('crypto_balances', 'value_usd', existing_type=sa.NUMERIC(precision=14, scale=2), nullable=False)
    op.drop_column('integrations', 'warnings')
