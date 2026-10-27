from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import Settings, get_settings
from app.core.errors import ApiError

# Only asymmetric algorithms: the token is checked with the provider's public key. Accepting
# HS256 here would let an attacker sign a token using that public key as if it were a secret.
ALGORITHMS = ["ES256", "RS256"]
AUDIENCE = "authenticated"
# Small tolerance for clock differences between this server and the provider.
CLOCK_SKEW_SECONDS = 10
JWKS_TIMEOUT_SECONDS = 5
JWKS_REFRESH_COOLDOWN_SECONDS = 60

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None


class InvalidToken(Exception):
    """The token is missing, malformed, expired, or not issued for this application."""


class KeysUnavailable(Exception):
    """The provider's public keys could not be fetched."""


class JwtVerifier:
    """Verifies access tokens issued by the authentication provider."""

    def __init__(self, issuer: str, key_for: Callable[[str], Any]) -> None:
        self.issuer = issuer
        self._key_for = key_for

    def verify(self, token: str) -> dict[str, Any]:
        try:
            key = self._key_for(token)
            return jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=AUDIENCE,
                issuer=self.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except jwt.PyJWKClientConnectionError as error:
            raise KeysUnavailable from error
        except jwt.PyJWTError as error:
            raise InvalidToken from error


@lru_cache
def build_verifier(supabase_url: str) -> JwtVerifier:
    """One verifier per project URL, so the downloaded public keys are cached between requests."""
    base = supabase_url.rstrip("/")
    keys = PyJWKClient(
        f"{base}/auth/v1/.well-known/jwks.json",
        timeout=JWKS_TIMEOUT_SECONDS,
        # A token with an unknown key id may trigger a new download, but not more than once in
        # this time, so made-up key ids cannot make the server fetch the key set on every request.
        cooldown_duration=JWKS_REFRESH_COOLDOWN_SECONDS,
    )
    return JwtVerifier(
        issuer=f"{base}/auth/v1",
        key_for=lambda token: keys.get_signing_key_from_jwt(token).key,
    )


def get_verifier(settings: Settings = Depends(get_settings)) -> JwtVerifier:
    if not settings.supabase_url:
        raise ApiError(503, "auth_not_configured", "La autenticación no está configurada.")
    return build_verifier(settings.supabase_url)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    verifier: JwtVerifier = Depends(get_verifier),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """Dependency for protected routes: returns the authenticated user or raises an ApiError."""
    challenge = {"WWW-Authenticate": "Bearer"}
    if credentials is None:
        raise ApiError(401, "unauthorized", "Inicia sesión para continuar.", headers=challenge)

    allowed_ids, allowed_emails = settings.allowed_users, settings.allowed_emails
    if not allowed_ids and not allowed_emails:
        # Fail closed: a valid account at the provider is not enough to read these finances.
        raise ApiError(503, "auth_not_configured", "No hay usuarios autorizados configurados.")

    try:
        claims = verifier.verify(credentials.credentials)
    except InvalidToken:
        raise ApiError(
            401, "invalid_token", "Tu sesión no es válida o venció. Inicia sesión de nuevo.", headers=challenge
        ) from None
    except KeysUnavailable:
        raise ApiError(503, "auth_unavailable", "No se pudo verificar tu sesión. Intenta de nuevo.") from None

    email = claims.get("email")
    is_allowed = claims["sub"] in allowed_ids or (isinstance(email, str) and email.lower() in allowed_emails)
    if not is_allowed:
        raise ApiError(403, "forbidden", "No tienes acceso a esta aplicación.")

    return CurrentUser(id=claims["sub"], email=email)
