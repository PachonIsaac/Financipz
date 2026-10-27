from sqlalchemy import text

from app.db.session import get_engine


def check_database(database_url: str) -> str:
    """Return the database status: 'ok', 'unreachable', or 'not_configured'.

    It reuses the application's shared engine, so a flood of calls to this public endpoint does
    not open a new connection each time.
    """
    if not database_url:
        return "not_configured"

    try:
        with get_engine(database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unreachable"
