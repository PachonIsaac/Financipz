"""revoke table access from the roles of the database REST layer

Revision ID: cbb0b0f8a19c
Revises: c7d4e9a01b52
Create Date: 2026-10-27 15:14:56.459417

Where the database is managed by a REST layer, that layer's roles receive access to every new
table by default. This application never uses them: only the backend, as the table owner, reads and
writes. Row level security already denies them, and this removes the privileges as well, for the
existing tables and for the ones created later by this role. On a database without those roles
(a local one, for example) it does nothing.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "cbb0b0f8a19c"
down_revision: Union[str, Sequence[str], None] = "c7d4e9a01b52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

API_ROLES = ("anon", "authenticated", "service_role")


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        DECLARE role_name text;
        BEGIN
            FOREACH role_name IN ARRAY ARRAY[{", ".join(repr(role) for role in API_ROLES)}] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', role_name);
                    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', role_name);
                END IF;
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    # Granting access back to roles this application does not use would only widen exposure.
    pass
