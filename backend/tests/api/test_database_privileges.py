import pytest
from sqlalchemy import text

API_ROLES = ("anon", "authenticated", "service_role")


def test_the_roles_of_the_rest_layer_have_no_access_to_any_table(db):
    present = [role for role in API_ROLES if db.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role})]
    if not present:
        pytest.skip("this database has none of those roles")

    grants = db.execute(
        text(
            "SELECT grantee, table_name FROM information_schema.role_table_grants "
            "WHERE table_schema = 'public' AND grantee = ANY(:roles)"
        ),
        {"roles": present},
    ).all()

    assert grants == []


def test_every_table_enforces_row_level_security(db):
    """A table added without enabling it would be readable by any role that is granted access."""
    without = db.execute(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity "
            "AND c.relname <> 'alembic_version'"
        )
    ).all()

    assert without == []
