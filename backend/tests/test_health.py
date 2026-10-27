from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app

client = TestClient(app)


def override_settings(database_url: str) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url=database_url,
        _env_file=None,
    )


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_health_reports_database_not_configured_without_url() -> None:
    override_settings("")

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "not_configured"}


def test_health_reports_database_unreachable_for_bad_url() -> None:
    override_settings("postgresql+psycopg://user:pass@127.0.0.1:1/none")

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "unreachable"}
