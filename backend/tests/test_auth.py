import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.core.auth import JwtVerifier, build_verifier, get_verifier
from app.core.config import Settings, get_settings
from app.main import app

BASE_URL = "https://project.example.test"
ISSUER = f"{BASE_URL}/auth/v1"
USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"

PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
PUBLIC_KEY = PRIVATE_KEY.public_key()
ATTACKER_KEY = ec.generate_private_key(ec.SECP256R1())

client = TestClient(app)


def configure(
    allowed_user_ids: str = USER_ID,
    allowed_user_emails: str = "",
    supabase_url: str = BASE_URL,
    key_for=lambda token: PUBLIC_KEY,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        supabase_url=supabase_url,
        allowed_user_ids=allowed_user_ids,
        allowed_user_emails=allowed_user_emails,
        _env_file=None,
    )
    app.dependency_overrides[get_verifier] = lambda: JwtVerifier(ISSUER, key_for)


@pytest.fixture(autouse=True)
def default_configuration():
    configure()
    yield
    app.dependency_overrides.clear()


def make_token(key=PRIVATE_KEY, **overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": USER_ID,
        "email": "user@example.test",
        "aud": "authenticated",
        "iss": ISSUER,
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    # Passing None removes a claim.
    claims = {name: value for name, value in claims.items() if value is not None}
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "test-key"})


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def forged_payload() -> str:
    claims = {"sub": USER_ID, "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 3600}
    return b64(json.dumps(claims).encode())


def token_with_alg_none() -> str:
    header = b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    return f"{header}.{forged_payload()}."


def token_hs256_signed_with_public_key() -> str:
    """Algorithm confusion attack: sign with HMAC using the public key as the secret."""
    secret = PUBLIC_KEY.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = forged_payload()
    signature = hmac.new(secret, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{b64(signature)}"


def get_me(token: str | None = None, scheme: str = "Bearer"):
    headers = {"Authorization": f"{scheme} {token}"} if token is not None else {}
    return client.get("/api/v1/me", headers=headers)


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_valid_token_returns_the_user():
    response = get_me(make_token())

    assert response.status_code == 200
    assert response.json() == {"id": USER_ID, "email": "user@example.test"}


def test_email_is_optional():
    response = get_me(make_token(email=None))

    assert response.status_code == 200
    assert response.json() == {"id": USER_ID, "email": None}


def test_missing_token_is_rejected_with_a_challenge():
    response = get_me()

    assert response.status_code == 401
    assert error_code(response) == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"
    assert set(response.json()["error"]) == {"code", "message", "details"}


def test_other_authorization_schemes_are_rejected():
    response = get_me("dXNlcjpwYXNz", scheme="Basic")

    assert response.status_code == 401
    assert error_code(response) == "unauthorized"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-jwt", id="garbage"),
        pytest.param(make_token(exp=int(time.time()) - 3600), id="expired"),
        pytest.param(make_token(aud="anon"), id="wrong-audience"),
        pytest.param(make_token(iss="https://evil.example.test/auth/v1"), id="wrong-issuer"),
        pytest.param(make_token(key=ATTACKER_KEY), id="signed-by-another-key"),
        pytest.param(make_token(exp=None), id="no-expiration"),
        pytest.param(make_token(sub=None), id="no-subject"),
        pytest.param(token_with_alg_none(), id="alg-none"),
        pytest.param(token_hs256_signed_with_public_key(), id="hs256-with-public-key"),
    ],
)
def test_invalid_tokens_are_rejected(token):
    response = get_me(token)

    assert response.status_code == 401
    assert error_code(response) == "invalid_token"
    assert response.headers["www-authenticate"] == "Bearer"


def test_token_just_expired_within_the_clock_skew_is_accepted():
    response = get_me(make_token(exp=int(time.time()) - 2))

    assert response.status_code == 200


def test_unknown_signing_key_is_an_invalid_token():
    def unknown_key(token):
        raise jwt.PyJWKClientError("Unable to find a signing key that matches")

    configure(key_for=unknown_key)

    response = get_me(make_token())

    assert response.status_code == 401
    assert error_code(response) == "invalid_token"


def test_unreachable_public_keys_are_a_service_error_not_a_login_error():
    def unreachable(token):
        raise jwt.PyJWKClientConnectionError("connection refused")

    configure(key_for=unreachable)

    response = get_me(make_token())

    assert response.status_code == 503
    assert error_code(response) == "auth_unavailable"


def test_allowed_user_gets_in():
    configure(allowed_user_ids=f"{OTHER_USER_ID}, {USER_ID}")

    assert get_me(make_token()).status_code == 200


def test_user_outside_the_allowlist_is_forbidden():
    configure(allowed_user_ids=OTHER_USER_ID)

    response = get_me(make_token())

    assert response.status_code == 403
    assert error_code(response) == "forbidden"


def test_without_any_allowed_user_nobody_gets_in_even_with_a_valid_token():
    configure(allowed_user_ids="", allowed_user_emails="")

    response = get_me(make_token())

    assert response.status_code == 503
    assert error_code(response) == "auth_not_configured"


def test_a_user_can_be_allowed_by_email_ignoring_case():
    configure(allowed_user_ids="", allowed_user_emails="USER@Example.test")

    assert get_me(make_token()).status_code == 200


def test_a_different_email_is_forbidden():
    configure(allowed_user_ids="", allowed_user_emails="someone.else@example.test")

    response = get_me(make_token())

    assert response.status_code == 403
    assert error_code(response) == "forbidden"


def test_a_token_without_email_cannot_match_the_email_list():
    configure(allowed_user_ids="", allowed_user_emails="user@example.test")

    assert get_me(make_token(email=None)).status_code == 403


def test_authentication_not_configured_fails_closed():
    app.dependency_overrides.pop(get_verifier)
    configure_settings_only = lambda: Settings(supabase_url="", _env_file=None)  # noqa: E731
    app.dependency_overrides[get_settings] = configure_settings_only

    response = get_me(make_token())

    assert response.status_code == 503
    assert error_code(response) == "auth_not_configured"


def test_verifier_is_built_from_the_project_url_and_reused():
    build_verifier.cache_clear()

    verifier = build_verifier("https://project.example.test/")

    assert verifier.issuer == "https://project.example.test/auth/v1"
    assert build_verifier("https://project.example.test/") is verifier


def test_health_stays_public():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
