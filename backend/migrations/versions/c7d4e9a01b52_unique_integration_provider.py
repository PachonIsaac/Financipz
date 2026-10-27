"""allow one integration row per provider

Revision ID: c7d4e9a01b52
Revises: b3f1c2a47d10
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c7d4e9a01b52'
down_revision: Union[str, Sequence[str], None] = 'b3f1c2a47d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('uq_integrations_provider', 'integrations', ['provider'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_integrations_provider', table_name='integrations')
