import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core import oauth_state
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_json
from app.db import models
from app.integrations import gmail
from app.main import app
from app.integrations.gmail import _text_of
from app.services import gmail_sync, integrations, refresh
from tests.api.google_fake import ALLOWED, FakeGoogle, html_message, kind_of, plain_message
from tests.api.helpers import API, create_account, error_code
from tests.api.test_ingest import FAILED, PURCHASE, with_digits

KEY = Fernet.generate_key().decode()
CALLBACK = f"{API}/integrations/gmail/callback"
APP = "https://app.test/Financipz/"


def configured(**overrides) -> Settings:
    values = dict(
        _env_file=None,
        encryption_key=KEY,
        google_client_id="client-id",
        google_client_secret="client-secret",
        google_redirect_uri="https://api.test/api/v1/integrations/gmail/callback",
        app_url=APP,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def forget_previous_refresh():
    refresh._last = None
    yield
    refresh._last = None


@pytest.fixture
def google(client, monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(gmail, "build_http", fake.client)
    app.dependency_overrides[get_settings] = lambda: configured()
    yield fake
    assert {kind_of(r) for r in fake.requests} <= ALLOWED


def connect_with_callback(client) -> str:
    state = oauth_state.make(KEY)
    response = client.get(CALLBACK, params={"code": "good-code", "state": state}, follow_redirects=False)
    assert response.status_code == 303, response.text
    return response.headers["location"]


@pytest.fixture
def connected(client, google):
    connect_with_callback(client)
    return google


def test_it_cannot_connect_until_the_server_has_the_provider_settings(client):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, encryption_key=KEY)

    response = client.post(f"{API}/integrations/gmail/connect")

    assert response.status_code == 503 and error_code(response) == "gmail_not_configured"


def test_the_consent_address_asks_for_read_only_offline_access_with_a_signed_state(client, google):
    url = client.post(f"{API}/integrations/gmail/connect").json()["authorization_url"]

    query = {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}
    assert urlparse(url).netloc == "accounts.google.com"
    assert query["scope"] == "https://www.googleapis.com/auth/gmail.readonly"
    assert (query["access_type"], query["prompt"], query["client_id"]) == ("offline", "consent", "client-id")
    assert oauth_state.valid(KEY, query["state"])


def test_coming_back_from_the_consent_page_stores_the_token_encrypted_and_returns_to_the_app(client, db, google):
    location = connect_with_callback(client)

    assert location == f"{APP}more/gmail?connected=1"
    row = integrations.get_row(db, "gmail")
    assert row.status == "active" and row.encrypted_secret is not None
    assert b"refresh-token-value" not in row.encrypted_secret
    assert decrypt_json(KEY, row.encrypted_secret) == {"refresh_token": "refresh-token-value"}


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"code": "good-code", "state": "forged.value"}, "invalid_state"),
        ({"code": "good-code"}, "invalid_state"),
        ({"error": "access_denied", "state": "x"}, "access_denied"),
        ({"code": "bad-code", "state": "VALID"}, "gmail_rejected"),
    ],
)
def test_a_return_that_is_not_valid_stores_nothing_and_says_why(client, db, google, params, reason):
    params = {key: (oauth_state.make(KEY) if value == "VALID" else value) for key, value in params.items()}

    response = client.get(CALLBACK, params=params, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"{APP}more/gmail?error={reason}"
    assert integrations.get_row(db, "gmail") is None


def test_the_state_expires_and_cannot_be_tampered_with():
    state = oauth_state.make(KEY, now=time.time() - 3600)

    assert not oauth_state.valid(KEY, state)
    fresh = oauth_state.make(KEY)
    assert oauth_state.valid(KEY, fresh)
    assert not oauth_state.valid("another-secret", fresh)
    body, signature = fresh.split(".")
    assert not oauth_state.valid(KEY, f"{body}.{signature[:-2]}xx")
    assert not oauth_state.valid(KEY, None) and not oauth_state.valid(KEY, "")


def test_reading_the_mail_stores_pending_movements_and_remembers_each_message(client, db, connected):
    card = with_digits(client, create_account(client, name="Card", type="credit_card"), "1234")
    connected.messages = {
        "m1": plain_message(PURCHASE),
        "m2": plain_message(FAILED),
        "m3": plain_message("Hola, este es un aviso que ninguna plantilla conoce"),
        "m4": html_message(PURCHASE.replace("12.300,00", "99.000,00")),
    }

    response = client.post(f"{API}/integrations/gmail/sync")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["processed"], body["created"], body["ignored"], body["unrecognized"], body["duplicates"]) == (4, 2, 1, 1, 0)
    movements = list(db.scalars(select(models.Transaction).order_by(models.Transaction.amount)))
    assert [(str(m.amount), m.status, m.source, str(m.account_id)) for m in movements] == [
        ("12300.00", "pending_review", "gmail", card["id"]),
        ("99000.00", "pending_review", "gmail", card["id"]),
    ]
    results = {row.message_id: row.result for row in db.scalars(select(models.ProcessedEmail))}
    assert results == {"m1": "ok", "m2": "ignored", "m3": "unrecognized", "m4": "ok"}
    assert all(row.sender and "bancolombia" in row.sender for row in db.scalars(select(models.ProcessedEmail)))

    again = client.post(f"{API}/integrations/gmail/sync").json()
    assert again["processed"] == 0 and len(list(db.scalars(select(models.Transaction)))) == 2


def test_the_first_read_goes_back_a_month_and_the_next_one_starts_a_day_before_the_last(client, db, connected):
    client.post(f"{API}/integrations/gmail/sync")
    first = connected.queries()[0]
    assert "from:(alertasynotificaciones@ayn.notificacionesbancolombia.com)" in first
    month_ago = int((datetime.now(UTC) - timedelta(days=30)).timestamp())
    assert abs(int(first.rsplit("after:", 1)[1]) - month_ago) < 120

    row = integrations.get_row(db, "gmail")
    synced = int((row.last_synced_at - timedelta(days=1)).timestamp())
    client.post(f"{API}/integrations/gmail/sync")
    assert int(connected.queries()[1].rsplit("after:", 1)[1]) == synced


def test_a_withdrawn_permission_is_reported_and_the_stored_token_is_dropped(client, db, connected):
    connected.token_error = "invalid_grant"

    response = client.post(f"{API}/integrations/gmail/sync")

    assert response.status_code == 409 and error_code(response) == "gmail_access_revoked"
    row = integrations.get_row(db, "gmail")
    assert (row.status, row.encrypted_secret) == ("error", None)
    assert [warning["code"] for warning in row.warnings] == ["access_revoked"]
    assert error_code(client.post(f"{API}/integrations/gmail/sync")) == "credentials_removed"


@pytest.mark.parametrize(("status", "code", "http"), [(401, "gmail_access_revoked", 409), (500, "gmail_unavailable", 502), (429, "gmail_rate_limited", 503)])
def test_failures_of_the_mail_api_are_reported_and_do_not_move_the_clock(client, db, connected, status, code, http):
    connected.api_status = status

    response = client.post(f"{API}/integrations/gmail/sync")

    assert (response.status_code, error_code(response)) == (http, code)
    if status != 401:
        assert integrations.get_row(db, "gmail").last_synced_at is None


def test_reading_without_a_connection_is_a_conflict(client, google):
    response = client.post(f"{API}/integrations/gmail/sync")

    assert response.status_code == 409 and error_code(response) == "integration_not_connected"


def test_disconnecting_withdraws_the_permission_and_deletes_the_token(client, db, connected):
    response = client.delete(f"{API}/integrations/gmail")

    assert response.status_code == 204
    assert connected.revoked == ["refresh-token-value"]
    row = integrations.get_row(db, "gmail")
    assert (row.status, row.encrypted_secret) == ("disconnected", None)


def test_the_refresh_reads_the_mail_too_and_reports_it_apart(client, db, connected):
    card = with_digits(client, create_account(client, name="Card", type="credit_card"), "1234")
    connected.messages = {"m1": plain_message(PURCHASE)}

    body = client.post(f"{API}/refresh").json()

    assert body["gmail"] == {"status": "ok", "code": None, "message": None}
    assert len(list(db.scalars(select(models.Transaction)))) == 1
    assert card["id"]


def test_the_refresh_does_not_fail_when_the_mail_is_not_connected(client, google):
    body = client.post(f"{API}/refresh").json()

    assert body["gmail"]["status"] == "not_connected"


def test_a_long_backlog_is_read_in_several_goes_without_losing_any_message(client, db, connected, monkeypatch):
    monkeypatch.setattr(gmail_sync, "MAX_FETCHED_PER_SYNC", 3)
    card = with_digits(client, create_account(client, name="Card", type="credit_card"), "1234")
    # Newest first, as the provider lists them: m7 is the newest, m1 the oldest. Each has its own amount.
    connected.messages = {
        f"m{n}": plain_message(PURCHASE.replace("12.300,00", f"{n}.000,00")) for n in range(7, 0, -1)
    }

    first = client.post(f"{API}/integrations/gmail/sync").json()
    assert (first["processed"], first["more"]) == (3, True)
    # The oldest were read first and the clock did not move, so nothing is skipped.
    assert integrations.get_row(db, "gmail").last_synced_at is None
    assert sorted(str(row.amount) for row in db.scalars(select(models.Transaction))) == ["1000.00", "2000.00", "3000.00"]

    second = client.post(f"{API}/integrations/gmail/sync").json()
    third = client.post(f"{API}/integrations/gmail/sync").json()

    assert (second["processed"], second["more"], third["processed"], third["more"]) == (3, True, 1, False)
    assert integrations.get_row(db, "gmail").last_synced_at is not None
    assert len(list(db.scalars(select(models.Transaction)))) == 7
    assert card["id"]


def test_listing_follows_the_pages_of_the_provider(client, db, connected):
    connected.messages = {f"m{n}": plain_message("sin plantilla") for n in range(250)}

    body = client.post(f"{API}/integrations/gmail/sync").json()

    # 250 messages need three pages; only 100 are fetched each time and the rest wait.
    assert (body["processed"], body["more"]) == (100, True)
    assert len([q for q in connected.queries()]) == 3


def test_a_message_that_only_claims_to_come_from_the_bank_is_not_read(client, db, connected):
    with_digits(client, create_account(client, name="Card", type="credit_card"), "1234")
    connected.messages = {
        "spoof": plain_message(PURCHASE, sender="evil@elsewhere.test"),
        "real": plain_message(PURCHASE.replace("12.300,00", "7.000,00")),
    }
    # A display name that looks like the bank, with another address behind it.
    connected.messages["spoof"]["payload"]["headers"][0]["value"] = "alertasynotificaciones@ayn.notificacionesbancolombia.com <evil@elsewhere.test>"

    body = client.post(f"{API}/integrations/gmail/sync").json()

    assert (body["created"], body["ignored"]) == (1, 1)
    assert [str(row.amount) for row in db.scalars(select(models.Transaction))] == ["7000.00"]


def test_hostile_markup_is_read_in_linear_time():
    from app.integrations import gmail as module
    from tests.api.google_fake import b64

    nasty = "<script<" * 400_000 + "<<<<<" * 200_000 + " Compraste COP1,00 "
    started = time.monotonic()
    text = _text_of({"mimeType": "text/html", "body": {"data": b64(nasty)}})

    assert time.monotonic() - started < 3
    assert len(text) <= module.MAX_BODY_CHARS


def test_a_state_works_once_and_must_have_been_issued_here(client, db, google):
    state = oauth_state.make(KEY)
    first = client.get(CALLBACK, params={"code": "good-code", "state": state}, follow_redirects=False)
    replay = client.get(CALLBACK, params={"code": "good-code", "state": state}, follow_redirects=False)
    forged = client.get(
        CALLBACK,
        params={"code": "good-code", "state": oauth_state.make(KEY).split(".")[0] + ".AAAA"},
        follow_redirects=False,
    )

    assert first.headers["location"].endswith("connected=1")
    assert replay.headers["location"].endswith("error=invalid_state")
    assert forged.headers["location"].endswith("error=invalid_state")


def test_connecting_again_withdraws_the_previous_permission(client, db, connected):
    connected.refresh_token = "second-token"
    connect_with_callback(client)

    assert connected.revoked == ["refresh-token-value"]
    assert decrypt_json(KEY, integrations.get_row(db, "gmail").encrypted_secret) == {"refresh_token": "second-token"}


def test_the_refresh_does_not_call_a_missing_provider_setting_an_error(client, db, connected):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, encryption_key=KEY)

    body = client.post(f"{API}/refresh").json()

    assert body["gmail"]["status"] == "not_connected"
