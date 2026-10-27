from collections.abc import Callable, Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError


CONNECT_TIMEOUT_SECONDS = 5
# A connection through a pooler can stall half-open (a lost packet): the client then waits for an
# answer that never comes. Keepalives make the operating system notice a dead connection and fail
# it, instead of waiting forever. `tcp_user_timeout` (milliseconds) does the same where supported.
KEEPALIVE_ARGS = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
    "tcp_user_timeout": 60_000,
}


@lru_cache
def get_engine(database_url: str) -> Engine:
    # Transaction-mode poolers do not support server-side prepared statements.
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        connect_args={"prepare_threshold": None, "connect_timeout": CONNECT_TIMEOUT_SECONDS, **KEEPALIVE_ARGS},
    )


def get_db(settings: Settings = Depends(get_settings)) -> Iterator[Session]:
    """One session per request. Services commit explicitly; anything uncommitted is rolled back."""
    if not settings.database_url:
        raise ApiError(503, "database_not_configured", "La base de datos no está configurada.")
    # expire_on_commit=False keeps objects readable after a commit without extra round trips.
    with Session(get_engine(settings.database_url), expire_on_commit=False) as session:
        yield session


SessionFactory = Callable[[], Session]


def session_factory(database_url: str) -> SessionFactory:
    """Opens independent sessions on the shared engine, for work that needs its own transactions."""
    engine = get_engine(database_url)
    return lambda: Session(engine, expire_on_commit=False)


def get_session_factory(settings: Settings = Depends(get_settings)) -> SessionFactory:
    if not settings.database_url:
        raise ApiError(503, "database_not_configured", "La base de datos no está configurada.")
    return session_factory(settings.database_url)
