"""Encryption at rest for third-party credentials.

The key lives in the backend environment and never in the database. Without a valid key nothing is
encrypted or decrypted: the functions fail closed with a standard error instead of storing plaintext.
"""

import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.errors import ApiError

UNREADABLE = (
    "credentials_unreadable",
    "No se pudieron descifrar las credenciales guardadas. Vuelve a conectar la integración.",
)


def _cipher(key: str) -> Fernet:
    if not key:
        raise ApiError(
            503,
            "encryption_not_configured",
            "El cifrado de credenciales no está configurado en el servidor.",
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        # The underlying error is not forwarded: it is about the key.
        raise ApiError(503, "encryption_key_invalid", "La clave de cifrado del servidor no es válida.") from None


def encrypt_json(key: str, payload: dict[str, str]) -> bytes:
    """Encrypt a JSON object as a single authenticated blob."""
    return _cipher(key).encrypt(json.dumps(payload).encode())


def decrypt_json(key: str, blob: bytes) -> dict[str, str]:
    """Decrypt what `encrypt_json` produced. A wrong key or a damaged blob is a 503, never a crash."""
    cipher = _cipher(key)
    try:
        data = json.loads(cipher.decrypt(bytes(blob)))
    except (InvalidToken, ValueError):
        raise ApiError(503, *UNREADABLE) from None
    if not isinstance(data, dict) or not all(isinstance(value, str) for value in data.values()):
        raise ApiError(503, *UNREADABLE)
    return data
