import logging

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db import models
from app.main import app
from tests.api.binance_fake import API_KEY, API_SECRET, error, safe_restrictions
from tests.api.helpers import API, error_code

URL = f"{API}/integrations/binance"
BODY = {"api_key": API_KEY, "api_secret": API_SECRET}


def connect(client, body=None):
    return client.put(URL, json=body or BODY)


def stored(db) -> models.Integration | None:
    return db.scalars(select(models.Integration).where(models.Integration.provider == "binance")).first()


def test_connect_stores_the_key_encrypted_and_answers_without_secrets(client, exchange, db):
    response = connect(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"provider": "binance", "status": "active", "last_synced_at": None, "warnings": []}
    assert API_KEY not in response.text and API_SECRET not in response.text
    row = stored(db)
    assert row.status == "active"
    assert API_KEY.encode() not in bytes(row.encrypted_secret)
    assert API_SECRET.encode() not in bytes(row.encrypted_secret)
    assert exchange.paths() == ["/sapi/v1/account/apiRestrictions"]


def test_a_key_without_ip_restriction_is_accepted_with_a_warning(client, exchange):
    exchange.restrictions = safe_restrictions(ipRestrict=False)

    response = connect(client)

    assert response.status_code == 200
    assert [warning["code"] for warning in response.json()["warnings"]] == ["ip_not_restricted"]


@pytest.mark.parametrize(
    "flag", ["enableWithdrawals", "enableInternalTransfer", "enableSpotAndMarginTrading", "enableSomethingNew"]
)
def test_a_key_that_can_do_more_than_read_is_refused_and_nothing_is_stored(client, exchange, db, flag):
    exchange.restrictions = safe_restrictions(**{flag: True})

    response = connect(client)

    assert response.status_code == 422
    assert error_code(response) == "binance_key_not_read_only"
    assert response.json()["error"]["details"] == {"permissions": [flag]}
    assert stored(db) is None


def test_a_refused_key_does_not_replace_the_stored_one(client, exchange, db):
    assert connect(client).status_code == 200
    before = bytes(stored(db).encrypted_secret)
    exchange.restrictions = safe_restrictions(enableWithdrawals=True)

    assert connect(client, {"api_key": "another-key-0002", "api_secret": "another-secret-0002"}).status_code == 422

    db.expire_all()
    assert bytes(stored(db).encrypted_secret) == before


def test_connecting_again_replaces_the_key_and_clears_old_warnings(client, exchange, db):
    exchange.restrictions = safe_restrictions(ipRestrict=False)
    connect(client)
    exchange.restrictions = safe_restrictions()

    response = connect(client, {"api_key": "another-key-0002", "api_secret": "another-secret-0002"})

    assert response.json()["warnings"] == []
    assert len(list(db.scalars(select(models.Integration)))) == 1


@pytest.mark.parametrize(
    ("answer", "status", "code"),
    [
        (error(400, -2014), 422, "binance_invalid_credentials"),
        (error(400, -1022), 422, "binance_invalid_credentials"),
        (error(401, -2015), 422, "binance_access_denied"),
        (error(400, -1021), 502, "binance_clock_skew"),
        (error(429, -1003), 503, "binance_rate_limited"),
        (error(503, -1000), 502, "binance_unavailable"),
        (lambda request: httpx.Response(200, text="<html>"), 502, "binance_bad_response"),
        (lambda request: httpx.Response(200, json=["not", "an", "object"]), 502, "binance_bad_response"),
    ],
)
def test_exchange_failures_become_standard_errors_and_store_nothing(client, exchange, db, answer, status, code):
    exchange.overrides["/sapi/v1/account/apiRestrictions"] = answer

    response = connect(client)

    assert response.status_code == status
    body = response.json()["error"]
    assert body["code"] == code
    assert API_KEY not in response.text and API_SECRET not in response.text
    assert stored(db) is None


def test_a_missing_encryption_key_fails_closed_before_calling_the_exchange(client, exchange, db):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, encryption_key="")

    response = connect(client)

    assert response.status_code == 503
    assert error_code(response) == "encryption_not_configured"
    assert exchange.requests == []
    assert stored(db) is None


def test_an_invalid_encryption_key_fails_closed(client, exchange):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, encryption_key="not-a-key")

    response = connect(client)

    assert response.status_code == 503
    assert error_code(response) == "encryption_key_invalid"
    assert "not-a-key" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {"api_key": API_KEY},
        {"api_key": "short", "api_secret": API_SECRET},
        {"api_key": "has spaces in it", "api_secret": API_SECRET},
        {"api_key": API_KEY, "api_secret": API_SECRET, "extra": "x"},
        {"api_key": "x" * 300, "api_secret": API_SECRET},
    ],
)
def test_invalid_bodies_are_rejected_without_echoing_secrets(client, exchange, body):
    response = connect(client, body)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert API_SECRET not in response.text and "has spaces" not in response.text
    assert exchange.requests == []


def test_secrets_are_never_logged(client, exchange, caplog):
    caplog.set_level(logging.DEBUG)
    exchange.restrictions = safe_restrictions(enableWithdrawals=True)

    connect(client)
    exchange.restrictions = safe_restrictions()
    connect(client)

    assert API_KEY not in caplog.text and API_SECRET not in caplog.text


def test_the_list_shows_every_provider_without_secrets(client, exchange):
    empty = client.get(f"{API}/integrations")
    connect(client)
    connected = client.get(f"{API}/integrations")

    assert empty.status_code == 200
    assert empty.json() == [
        {"provider": "gmail", "status": "disconnected", "last_synced_at": None, "warnings": []},
        {"provider": "binance", "status": "disconnected", "last_synced_at": None, "warnings": []},
    ]
    assert connected.json()[1] == {"provider": "binance", "status": "active", "last_synced_at": None, "warnings": []}
    assert "secret" not in connected.text and API_KEY not in connected.text


def test_disconnect_removes_the_credentials_and_is_idempotent(client, exchange, db):
    connect(client)

    first = client.delete(URL)
    second = client.delete(URL)

    assert first.status_code == 204 and second.status_code == 204
    db.expire_all()
    row = stored(db)
    assert row.encrypted_secret is None
    assert row.status == "disconnected"
    assert client.get(f"{API}/integrations").json()[1]["status"] == "disconnected"


def test_disconnecting_without_ever_connecting_is_fine(client, exchange):
    assert client.delete(URL).status_code == 204
