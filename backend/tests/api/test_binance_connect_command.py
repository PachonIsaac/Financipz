from sqlalchemy import select

from app.db import models
from app.integrations import binance_connect
from tests.api.binance_fake import API_KEY, API_SECRET, safe_restrictions


def run_command(db, exchange, monkeypatch, answers: list[str]) -> int:
    class FakeSettings:
        database_url = "postgresql+psycopg://invented"
        encryption_key = exchange.encryption_key

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return db

        def __exit__(self, *args):
            return False

    prompts: list[str] = []

    def fake_getpass(prompt: str = "") -> str:
        prompts.append(prompt)
        return answers.pop(0)

    monkeypatch.setattr(binance_connect, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(binance_connect, "get_engine", lambda url: None)
    monkeypatch.setattr(binance_connect, "Session", FakeSession)
    monkeypatch.setattr(binance_connect, "getpass", fake_getpass)
    return binance_connect.main()


def test_the_command_reads_hidden_input_and_stores_the_key_encrypted(client, exchange, db, monkeypatch, capsys):
    exchange.restrictions = safe_restrictions(ipRestrict=False)

    code = run_command(db, exchange, monkeypatch, [f"  {API_KEY} ", API_SECRET])

    output = capsys.readouterr()
    assert code == 0
    assert "ip_not_restricted" in output.out
    assert API_KEY not in output.out + output.err and API_SECRET not in output.out + output.err
    row = db.scalars(select(models.Integration)).one()
    assert row.status == "active"
    assert API_KEY.encode() not in bytes(row.encrypted_secret)


def test_the_command_refuses_a_key_with_dangerous_permissions(client, exchange, db, monkeypatch, capsys):
    exchange.restrictions = safe_restrictions(enableWithdrawals=True)

    code = run_command(db, exchange, monkeypatch, [API_KEY, API_SECRET])

    output = capsys.readouterr()
    assert code == 1
    assert "binance_key_not_read_only" in output.err and "enableWithdrawals" in output.err
    assert db.scalars(select(models.Integration)).first() is None


def test_the_command_needs_both_values(client, exchange, db, monkeypatch, capsys):
    code = run_command(db, exchange, monkeypatch, [API_KEY, "   "])

    assert code == 2
    assert exchange.requests == []
