"""let a movement wait for review without an account

Revision ID: e4b7c2d9a1f6
Revises: d1a8f3c5e920
Create Date: 2026-10-28 18:00:00.000000

A notification that does not say which account it belongs to is stored as pending, with no account, until
the person chooses one. The new rule keeps such a movement from being confirmed. Existing rows all have an
account, so nothing changes for them.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e4b7c2d9a1f6"
down_revision: Union[str, Sequence[str], None] = "d1a8f3c5e920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("transactions", "account_id", nullable=True)
    op.create_check_constraint(
        "account_required_when_confirmed", "transactions", "account_id IS NOT NULL OR status <> 'confirmed'"
    )


def downgrade() -> None:
    # Movements without an account cannot exist in the old shape, and they are never deleted silently.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM transactions WHERE account_id IS NULL) THEN
                RAISE EXCEPTION 'Assign or discard the movements without an account before going back';
            END IF;
        END $$;
        """
    )
    op.drop_constraint("account_required_when_confirmed", "transactions", type_="check")
    op.alter_column("transactions", "account_id", nullable=False)
