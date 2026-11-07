import uuid
from datetime import datetime

from app.domain.entities import LOCAL_TIMEZONE
from tests.api.helpers import API, D, balance_of, create_account, create_transaction, error_code


def adjust(client, account, observed, note="Counted the cash", **extra):
    return client.post(
        f"{API}/accounts/{account['id']}/adjustments",
        json={"observed_balance": str(observed), "note": note, **extra},
    )


def test_observed_above_the_balance_records_an_adjustment_in(client):
    cash = create_account(client, name="Cash", type="cash", initial=1000)

    response = adjust(client, cash, 1250)

    assert response.status_code == 201
    body = response.json()
    assert body["transaction"]["type"] == "adjustment_in"
    assert body["transaction"]["amount"] == "250.00"
    assert body["transaction"]["note"] == "Counted the cash"
    assert D(body["balance"]) == D("1250")
    assert balance_of(client, cash) == D("1250")


def test_observed_below_the_balance_records_an_adjustment_out_with_a_positive_amount(client):
    cash = create_account(client, name="Cash", type="cash", initial=1000)

    response = adjust(client, cash, 700)

    assert response.json()["transaction"]["type"] == "adjustment_out"
    assert response.json()["transaction"]["amount"] == "300.00"
    assert balance_of(client, cash) == D("700")


def test_matching_balance_records_nothing(client):
    cash = create_account(client, name="Cash", type="cash", initial=1000)

    response = adjust(client, cash, "1000.00")

    assert response.status_code == 200
    assert response.json()["transaction"] is None
    assert D(response.json()["balance"]) == D("1000")


def test_adjustment_works_from_the_current_balance_with_negative_values(client):
    card = create_account(client, name="Card", type="credit_card")
    create_transaction(client, card, "expense", 500)

    response = adjust(client, card, -300, note="Statement balance")

    assert response.json()["transaction"]["type"] == "adjustment_in"
    assert response.json()["transaction"]["amount"] == "200.00"
    assert balance_of(client, card) == D("-300")


def test_a_note_is_required(client):
    cash = create_account(client, name="Cash", type="cash", initial=1000)

    blank = adjust(client, cash, 900, note="   ")
    assert blank.status_code == 422
    assert error_code(blank) == "adjustment_note_required"

    missing = client.post(f"{API}/accounts/{cash['id']}/adjustments", json={"observed_balance": "900"})
    assert missing.status_code == 422

    assert balance_of(client, cash) == D("1000")


def test_archived_accounts_cannot_be_adjusted(client):
    cash = create_account(client, name="Cash", type="cash", initial=1000)
    client.patch(f"{API}/accounts/{cash['id']}", json={"archived": True})

    response = adjust(client, cash, 900)

    assert response.status_code == 409
    assert error_code(response) == "account_archived"


def test_unknown_account_is_not_found(client):
    response = client.post(
        f"{API}/accounts/{uuid.uuid4()}/adjustments", json={"observed_balance": "10", "note": "x"}
    )

    assert response.status_code == 404


def interest(client, account, observed, **extra):
    return client.post(
        f"{API}/accounts/{account['id']}/adjustments", json={"observed_balance": str(observed), "as_interest": True, **extra}
    )


def month_summary(client):
    return client.get(f"{API}/summary", params={"month": datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m")}).json()


def test_a_higher_balance_can_be_recorded_as_interest_which_counts_as_income(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=100_000)

    response = interest(client, wallet, 100_350)

    assert response.status_code == 201, response.text
    body = response.json()["transaction"]
    assert (body["type"], body["amount"], body["status"], body["merchant"], body["source"]) == (
        "income", "350.00", "confirmed", "Intereses", "manual",
    )
    assert body["category_id"] is not None
    assert balance_of(client, wallet) == D("100350")
    income = month_summary(client)["income"]
    assert income == "350.00"
    names = {item["category_id"]: item["name"] for item in month_summary(client)["income_by_category"]}
    assert names[body["category_id"]] == "Rendimientos"


def test_interest_uses_the_existing_category_for_returns_and_needs_no_note(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=1000)
    category = client.post(f"{API}/categories", json={"name": "Rendimientos", "type": "income"}).json()

    first = interest(client, wallet, 1010).json()["transaction"]
    second = interest(client, wallet, 1025, note="Rendimiento de la semana").json()["transaction"]

    assert first["category_id"] == second["category_id"] == category["id"]
    assert (first["note"], second["note"]) == (None, "Rendimiento de la semana")


def test_a_lower_or_equal_balance_cannot_be_interest_and_changes_nothing(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=1000)

    lower = interest(client, wallet, 900)
    same = interest(client, wallet, 1000)

    assert lower.status_code == 422 and error_code(lower) == "interest_must_be_positive"
    assert same.status_code == 200 and same.json()["transaction"] is None
    assert balance_of(client, wallet) == D("1000")


def test_a_positive_adjustment_made_before_can_be_marked_as_interest(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=1000)
    adjustment = adjust(client, wallet, 1500, note="Counted").json()["transaction"]
    before = balance_of(client, wallet)

    response = client.post(f"{API}/transactions/{adjustment['id']}/mark-interest")

    assert response.status_code == 200, response.text
    assert (response.json()["type"], response.json()["amount"]) == ("income", "500.00")
    assert response.json()["category_id"] is not None and response.json()["note"] == "Counted"
    assert balance_of(client, wallet) == before == D("1500")
    assert month_summary(client)["income"] == "500.00"


def test_only_a_positive_confirmed_adjustment_can_be_marked_as_interest(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=1000)
    negative = adjust(client, wallet, 800, note="Counted").json()["transaction"]
    expense = create_transaction(client, wallet, "expense", 10)

    for target in (negative["id"], expense["id"]):
        response = client.post(f"{API}/transactions/{target}/mark-interest")
        assert response.status_code == 409 and error_code(response) == "not_a_positive_adjustment"
    assert client.post(f"{API}/transactions/{uuid.uuid4()}/mark-interest").status_code == 404
