import pytest
from cryptography.fernet import Fernet

from app.core.crypto import decrypt_json, encrypt_json
from app.core.errors import ApiError

KEY = Fernet.generate_key().decode()
PAYLOAD = {"api_key": "invented-key-0001", "api_secret": "invented-secret-0001"}


def test_round_trip():
    assert decrypt_json(KEY, encrypt_json(KEY, PAYLOAD)) == PAYLOAD


def test_ciphertext_does_not_contain_the_plaintext():
    blob = encrypt_json(KEY, PAYLOAD)

    assert b"invented-key-0001" not in blob
    assert b"invented-secret-0001" not in blob
    assert b"api_secret" not in blob


def test_wrong_key_fails_with_a_standard_error():
    blob = encrypt_json(KEY, PAYLOAD)

    with pytest.raises(ApiError) as caught:
        decrypt_json(Fernet.generate_key().decode(), blob)

    assert caught.value.status_code == 503
    assert caught.value.code == "credentials_unreadable"
    assert "invented" not in caught.value.message


def test_damaged_blob_fails():
    with pytest.raises(ApiError) as caught:
        decrypt_json(KEY, b"not a token")

    assert caught.value.code == "credentials_unreadable"


def test_missing_key_fails_closed():
    with pytest.raises(ApiError) as caught:
        encrypt_json("", PAYLOAD)

    assert caught.value.status_code == 503
    assert caught.value.code == "encryption_not_configured"


@pytest.mark.parametrize("bad_key", ["short", "x" * 44, "not-base64-at-all!!"])
def test_invalid_key_fails_closed_without_echoing_it(bad_key):
    with pytest.raises(ApiError) as caught:
        encrypt_json(bad_key, PAYLOAD)

    assert caught.value.status_code == 503
    assert caught.value.code == "encryption_key_invalid"
    assert bad_key not in caught.value.message
    assert bad_key not in str(caught.value.details)


def test_blob_that_is_not_a_json_object_is_refused():
    blob = Fernet(KEY.encode()).encrypt(b'["a"]')

    with pytest.raises(ApiError) as caught:
        decrypt_json(KEY, blob)

    assert caught.value.code == "credentials_unreadable"
