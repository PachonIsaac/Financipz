import pytest
from sqlalchemy import select

from app.api import ingest as ingest_api
from app.core.ratelimit import RateLimiter
from app.db import models
from tests.api.helpers import API, create_account, error_code

SHORTCUT = f"{API}/ingest/shortcut"
ROTATE = f"{SHORTCUT}/token/rotate"
STATUS = f"{SHORTCUT}/token"
SMS = "Ualá Pagaste $50000 en TIENDA EJEMPLO MEDELLIN COL 🏦"
BODY = {"source": "sms_uala", "text": SMS, "received_at": "2026-10-27T14:32:00-05:00"}


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    monkeypatch.setattr(ingest_api, "requests_limit", RateLimiter(limit=60, window=60))
    monkeypatch.setattr(ingest_api, "failures_limit", RateLimiter(limit=10, window=60))


@pytest.fixture
def token(client):
    response = client.post(ROTATE)
    assert response.status_code == 201, response.text
    return response.json()["token"]


def send(client, token, body=BODY):
    return client.post(SHORTCUT, json=body, headers={"X-Ingest-Token": token} if token else {})


def test_a_new_token_is_shown_once_and_only_its_hash_is_stored(client, db, token):
    assert token.startswith("fzi_") and len(token) > 40
    stored = db.scalars(select(models.IngestToken)).one()
    assert token not in stored.token_hash and stored.token_hash != token

    status = client.get(STATUS).json()

    assert status["configured"] is True and status["last_used_at"] is None
    assert token not in str(status)


def test_rotating_invalidates_the_previous_token(client, token):
    new = client.post(ROTATE).json()["token"]

    assert send(client, token).status_code == 401
    assert send(client, new).status_code != 401


def test_without_a_token_or_with_a_wrong_one_nothing_is_stored(client, db, token):
    create_account(client, name="Wallet", type="wallet")

    for bad in (None, "", "fzi_wrong", token[:-1] + "x", "no-prefix"):
        response = send(client, bad)
        assert response.status_code == 401, bad
        assert error_code(response) == "invalid_ingest_token"
    assert list(db.scalars(select(models.Transaction))) == []


def test_no_token_configured_refuses_everything(client):
    assert send(client, "fzi_anything").status_code == 401


def test_an_sms_creates_a_pending_movement_on_the_wallet(client, db, token):
    wallet = create_account(client, name="Wallet", type="wallet")

    response = send(client, token)

    assert response.status_code == 201, response.text
    row = db.scalars(select(models.Transaction)).one()
    assert response.json() == {"result": "created", "id": str(row.id)}
    assert (str(row.account_id), row.type, row.status, row.source) == (wallet["id"], "expense", "pending_review", "sms_uala")
    assert str(row.amount) == "50000.00" and row.merchant == "TIENDA EJEMPLO MEDELLIN"
    assert client.get(STATUS).json()["last_used_at"] is not None


def test_sending_the_same_sms_again_is_a_conflict_that_names_the_stored_one(client, db, token):
    create_account(client, name="Wallet", type="wallet")
    first = send(client, token).json()

    second = send(client, token)

    assert second.status_code == 409 and error_code(second) == "duplicate_notification"
    assert second.json()["error"]["details"]["id"] == first["id"]
    assert len(list(db.scalars(select(models.Transaction)))) == 1


def test_a_text_nobody_understands_is_refused_and_stores_nothing(client, db, token):
    response = send(client, token, {**BODY, "text": "Hola, esto no es un movimiento"})

    assert response.status_code == 422 and error_code(response) == "unrecognized_notification"
    assert list(db.scalars(select(models.Transaction))) == []


def test_only_known_sources_and_bounded_texts_are_accepted(client, token):
    assert send(client, token, {**BODY, "source": "gmail"}).status_code == 422
    assert send(client, token, {**BODY, "text": "x" * 2001}).status_code == 422
    assert send(client, token, {**BODY, "text": ""}).status_code == 422


def test_a_time_without_a_zone_is_taken_as_colombian_time(client, db, token):
    create_account(client, name="Wallet", type="wallet")

    send(client, token, {**BODY, "received_at": "2026-10-27T14:32:00"})

    row = db.scalars(select(models.Transaction)).one()
    assert row.date.isoformat().startswith("2026-10-27T19:32:00")  # 14:32 in Colombia is 19:32 UTC


def test_guessing_the_token_is_cut_off(client, token):
    codes = [send(client, "fzi_guess").status_code for _ in range(12)]

    assert codes[:10] == [401] * 10
    assert codes[10:] == [429, 429]
    # Even the right token waits: the limit is on failures, not on who is asking.
    assert send(client, token).status_code in (201, 409, 422)


def test_a_runaway_shortcut_is_limited(client, token, monkeypatch):
    monkeypatch.setattr(ingest_api, "requests_limit", RateLimiter(limit=3, window=60))

    codes = [send(client, token).status_code for _ in range(5)]

    assert codes[3:] == [429, 429]


def test_junk_requests_cannot_use_up_the_limit_of_the_real_shortcut(client, token, monkeypatch):
    monkeypatch.setattr(ingest_api, "requests_limit", RateLimiter(limit=3, window=60))

    for _ in range(20):
        send(client, "fzi_junk")

    assert send(client, token).status_code != 429
