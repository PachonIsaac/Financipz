import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.integrations import binance
from app.main import app
from tests.api.binance_fake import FakeExchange

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DATABASE_NAME = "financipz_test"


def test_database_url() -> str | None:
    """TEST_DATABASE_URL if set, else the configured server with a separate `_test` database."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    configured = get_settings().database_url
    if not configured:
        return None
    return make_url(configured).set(database=TEST_DATABASE_NAME).render_as_string(hide_password=False)


def migrate(url: str) -> None:
    """Bring the test database to the latest schema. Alembic reads DATABASE_URL from the environment."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="session")
def test_connection() -> Iterator[Connection]:
    url = test_database_url()
    if url is None:
        pytest.skip("No database configured for integration tests")
    # Tests create and roll back data: never let them touch the real database.
    assert str(make_url(url).database).endswith("_test"), "Refusing to run tests on a non-test database"

    migrate(url)
    engine = create_engine(url, connect_args={"prepare_threshold": None})
    with engine.connect() as connection:
        yield connection
    engine.dispose()


def new_session(connection: Connection) -> Session:
    # Commits inside the application release a savepoint; the outer transaction is rolled back after each test.
    return Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def connection(test_connection: Connection) -> Iterator[Connection]:
    outer = test_connection.begin()
    yield test_connection
    outer.rollback()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    """A session for setting up data directly, the way another part of the system would."""
    with new_session(connection) as session:
        yield session


@pytest.fixture
def client(connection: Connection) -> Iterator[TestClient]:
    def request_session() -> Iterator[Session]:
        # A new session per request, like in production, so nothing is shared through the identity map.
        with new_session(connection) as session:
            yield session

    app.dependency_overrides[get_db] = request_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="test-user", email=None)
    yield TestClient(app)
    app.dependency_overrides.clear()


ENCRYPTION_TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
def exchange(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> FakeExchange:
    """A fake exchange behind the Binance client, an encryption key, and a fixed day."""
    fake = FakeExchange()
    monkeypatch.setattr(binance, "build_client", fake.client)
    monkeypatch.setattr("app.services.binance_sync.local_today", lambda: date(2026, 10, 27))
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, encryption_key=ENCRYPTION_TEST_KEY)
    return fake
