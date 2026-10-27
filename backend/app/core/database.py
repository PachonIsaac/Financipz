from sqlalchemy import create_engine, text


def check_database(database_url: str) -> str:
    """Return the database status: 'ok', 'unreachable', or 'not_configured'."""
    if not database_url:
        return "not_configured"

    # Connection poolers in transaction mode do not support server-side
    # prepared statements, so they are disabled here.
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unreachable"
    finally:
        engine.dispose()
