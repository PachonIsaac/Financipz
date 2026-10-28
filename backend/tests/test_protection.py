import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.auth import JwtVerifier, get_verifier
from app.core.config import Settings, get_settings
from app.main import app

# The shortcut route is not behind a session: it has its own token (see test_ingest_shortcut_api).
PUBLIC = {("GET", "/api/v1/health"), ("POST", "/api/v1/ingest/shortcut")}


def operations() -> list[tuple[str, str]]:
    found = []
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            if (method.upper(), path) not in PUBLIC:
                found.append((method.upper(), path))
    return sorted(found)


@pytest.fixture
def anonymous_client():
    app.dependency_overrides[get_settings] = lambda: Settings(supabase_url="https://project.example.test", _env_file=None)
    app.dependency_overrides[get_verifier] = lambda: JwtVerifier("https://project.example.test/auth/v1", lambda token: None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_list_of_protected_operations_is_not_empty():
    assert len(operations()) >= 19


@pytest.mark.parametrize(("method", "path"), operations())
def test_every_operation_except_health_requires_a_session(anonymous_client, method, path):
    url = path
    for name in ("account_id", "category_id", "transaction_id"):
        url = url.replace("{" + name + "}", str(uuid.uuid4()))

    response = anonymous_client.request(method, url)

    assert response.status_code == 401, f"{method} {path} answered {response.status_code}"
    assert response.json()["error"]["code"] == "unauthorized"


def test_unknown_routes_and_methods_use_the_standard_error_shape(anonymous_client):
    missing = anonymous_client.get("/api/v1/nowhere")
    wrong_method = anonymous_client.post("/api/v1/health")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "method_not_allowed"
