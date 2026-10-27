import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import models
from app.domain.entities import LOCAL_TIMEZONE

D = Decimal
API = "/api/v1"


def create_account(client: TestClient, name: str = "Bank", type: str = "bank", currency: str = "COP",
                   initial: str | int = 0, **extra) -> dict:
    response = client.post(
        f"{API}/accounts",
        json={"name": name, "type": type, "currency": currency, "initial_balance": str(initial), **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_category(client: TestClient, name: str = "Food", type: str = "expense", **extra) -> dict:
    response = client.post(f"{API}/categories", json={"name": name, "type": type, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def create_transaction(client: TestClient, account: dict, type: str = "expense", amount: str | int = 100,
                       **extra) -> dict:
    response = client.post(
        f"{API}/transactions",
        json={"account_id": account["id"], "type": type, "amount": str(amount), **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def balance_of(client: TestClient, account: dict) -> Decimal:
    response = client.get(f"{API}/accounts/{account['id']}")
    assert response.status_code == 200, response.text
    return D(response.json()["balance"])


def error_code(response) -> str:
    return response.json()["error"]["code"]


def add_rate(db: Session, day: date, value: str, currency: str = "USD") -> None:
    db.add(models.FxRate(date=day, currency=currency, value=D(value), source="test"))
    db.commit()


def insert_transaction(db: Session, account_id: str, *, type: str = "expense", amount: str = "10",
                       status: str = "pending_review", source: str = "gmail",
                       when: datetime | None = None, currency: str = "COP",
                       target_account_id: str | None = None, classification: str | None = None) -> str:
    """A movement as an automatic source would leave it, which the API cannot create."""
    row = models.Transaction(
        id=uuid.uuid4(),
        account_id=uuid.UUID(account_id),
        target_account_id=uuid.UUID(target_account_id) if target_account_id else None,
        classification=classification,
        type=type,
        amount=D(amount),
        currency=currency,
        date=when or datetime(2026, 10, 15, 12, 0, tzinfo=LOCAL_TIMEZONE),
        source=source,
        status=status,
    )
    db.add(row)
    db.commit()
    return str(row.id)
