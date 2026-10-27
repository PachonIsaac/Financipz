import uuid

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
