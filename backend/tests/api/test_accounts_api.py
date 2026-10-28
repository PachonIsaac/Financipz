import uuid

import pytest

from tests.api.helpers import API, D, balance_of, create_account, create_transaction, error_code


def test_create_account_starts_with_its_initial_balance(client):
    response = client.post(
        f"{API}/accounts",
        json={"name": "  Savings  ", "type": "savings", "currency": "COP", "initial_balance": "250000.50"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Savings"
    assert body["balance"] == "250000.50"
    assert body["archived"] is False
    assert body["key"] is None


def test_balance_follows_confirmed_movements(client):
    bank = create_account(client, initial=1000)
    create_transaction(client, bank, "income", 500)
    create_transaction(client, bank, "expense", 200)

    assert balance_of(client, bank) == D("1300")


def test_list_accounts_can_hide_archived_ones(client):
    active = create_account(client, name="Active")
    old = create_account(client, name="Old")
    client.patch(f"{API}/accounts/{old['id']}", json={"archived": True})

    everything = {account["id"] for account in client.get(f"{API}/accounts").json()}
    visible = {account["id"] for account in client.get(f"{API}/accounts?archived=false").json()}

    assert {active["id"], old["id"]} <= everything
    assert active["id"] in visible
    assert old["id"] not in visible


def test_key_is_stored_in_lowercase_and_is_unique_ignoring_case(client):
    first = create_account(client, key="@MiLlave")
    assert first["key"] == "@millave"

    response = client.post(
        f"{API}/accounts",
        json={"name": "Other", "type": "bank", "currency": "COP", "key": "@MILLAVE"},
    )

    assert response.status_code == 409
    assert error_code(response) == "account_key_taken"


def test_loan_account_needs_a_counterparty(client):
    response = client.post(f"{API}/accounts", json={"name": "Loan", "type": "loan", "currency": "COP"})
    assert response.status_code == 422
    assert error_code(response) == "counterparty_required"

    loan = create_account(client, name="Loan", type="loan", counterparty="Ana")
    assert loan["counterparty"] == "Ana"


def test_counterparty_only_applies_to_loans(client):
    response = client.post(
        f"{API}/accounts",
        json={"name": "Bank", "type": "bank", "currency": "COP", "counterparty": "Ana"},
    )

    assert response.status_code == 422
    assert error_code(response) == "counterparty_not_allowed"


def test_system_accounts_cannot_be_created_by_hand(client):
    response = client.post(f"{API}/accounts", json={"name": "System", "type": "system", "currency": "COP"})

    assert response.status_code == 422
    assert error_code(response) == "invalid_account_type"


def test_unknown_fields_and_bad_values_are_validation_errors(client):
    response = client.post(
        f"{API}/accounts",
        json={"name": "", "type": "piggy_bank", "currency": "EUR", "color": "red"},
    )

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    fields = {item["field"] for item in response.json()["error"]["details"]["fields"]}
    assert {"name", "type", "currency", "color"} <= fields


def test_update_name_clear_key_and_archive(client):
    account = create_account(client, key="@clave")

    response = client.patch(
        f"{API}/accounts/{account['id']}", json={"name": "Renamed", "key": None, "archived": True}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["key"] is None
    assert body["archived"] is True


def test_fields_that_cannot_be_empty_reject_null(client):
    account = create_account(client)

    response = client.patch(f"{API}/accounts/{account['id']}", json={"name": None})

    assert response.status_code == 422
    assert error_code(response) == "validation_error"


def test_currency_cannot_be_changed(client):
    account = create_account(client)

    response = client.patch(f"{API}/accounts/{account['id']}", json={"currency": "USD"})

    assert response.status_code == 422


def test_changing_the_opening_balance_changes_the_balance(client):
    account = create_account(client, initial=100)
    create_transaction(client, account, "expense", 30)

    response = client.patch(f"{API}/accounts/{account['id']}", json={"initial_balance": "500"})

    assert D(response.json()["balance"]) == D("470")


def test_type_can_switch_between_everyday_types_only(client):
    account = create_account(client, type="bank")

    allowed = client.patch(f"{API}/accounts/{account['id']}", json={"type": "savings"})
    assert allowed.status_code == 200
    assert allowed.json()["type"] == "savings"

    blocked = client.patch(f"{API}/accounts/{account['id']}", json={"type": "exchange"})
    assert blocked.status_code == 422
    assert error_code(blocked) == "account_type_locked"


def test_unknown_account_is_not_found(client):
    response = client.get(f"{API}/accounts/{uuid.uuid4()}")

    assert response.status_code == 404
    assert error_code(response) == "not_found"
    assert set(response.json()["error"]) == {"code", "message", "details"}


def test_malformed_id_is_a_validation_error(client):
    response = client.get(f"{API}/accounts/not-a-uuid")

    assert response.status_code == 422
    assert error_code(response) == "validation_error"


def test_accounts_cannot_be_deleted(client):
    account = create_account(client)

    assert client.delete(f"{API}/accounts/{account['id']}").status_code == 405


def test_identifiers_are_replaced_as_a_whole(client):
    account = create_account(client)
    url = f"{API}/accounts/{account['id']}/identifiers"

    assert client.get(url).json() == []

    saved = client.put(
        url,
        json={"identifiers": [{"digits": "2222", "type": "debit"}, {"digits": "1111", "type": "account"}]},
    )
    assert saved.status_code == 200
    assert [item["digits"] for item in saved.json()] == ["1111", "2222"]

    replaced = client.put(url, json={"identifiers": [{"digits": "3333", "type": "credit"}]})
    assert [item["digits"] for item in replaced.json()] == ["3333"]
    assert [item["digits"] for item in client.get(url).json()] == ["3333"]


def test_same_digits_cannot_belong_to_two_accounts(client):
    first = create_account(client, name="First")
    second = create_account(client, name="Second")
    client.put(f"{API}/accounts/{first['id']}/identifiers", json={"identifiers": [{"digits": "4444", "type": "debit"}]})

    response = client.put(
        f"{API}/accounts/{second['id']}/identifiers", json={"identifiers": [{"digits": "4444", "type": "debit"}]}
    )

    assert response.status_code == 409
    assert error_code(response) == "identifier_taken"
    assert response.json()["error"]["details"] == {"digits": ["4444"]}


def test_a_card_in_pesos_and_in_dollars_can_share_its_digits(client):
    pesos = create_account(client, name="Card COP", type="credit_card")
    dollars = create_account(client, name="Card USD", type="credit_card", currency="USD")
    digits = {"identifiers": [{"digits": "5555", "type": "credit"}]}

    assert client.put(f"{API}/accounts/{pesos['id']}/identifiers", json=digits).status_code == 200
    assert client.put(f"{API}/accounts/{dollars['id']}/identifiers", json=digits).status_code == 200

    another_in_pesos = create_account(client, name="Other COP", type="credit_card")
    clash = client.put(f"{API}/accounts/{another_in_pesos['id']}/identifiers", json=digits)
    assert clash.status_code == 409
    assert error_code(clash) == "identifier_taken"


@pytest.mark.parametrize(
    "identifiers",
    [
        [{"digits": "12", "type": "debit"}],
        [{"digits": "abcd", "type": "debit"}],
        [{"digits": "1234", "type": "savings"}],
    ],
)
def test_identifiers_are_four_digits_with_a_known_type(client, identifiers):
    account = create_account(client)

    response = client.put(f"{API}/accounts/{account['id']}/identifiers", json={"identifiers": identifiers})

    assert response.status_code == 422


def test_repeated_digits_in_one_request_are_rejected(client):
    account = create_account(client)

    response = client.put(
        f"{API}/accounts/{account['id']}/identifiers",
        json={"identifiers": [{"digits": "1111", "type": "debit"}, {"digits": "1111", "type": "credit"}]},
    )

    assert response.status_code == 422
    assert error_code(response) == "duplicate_identifier"


def test_accounts_count_toward_the_balance_by_default_and_can_be_left_out(client):
    account = create_account(client)
    assert account["include_in_balance"] is True

    response = client.patch(f"{API}/accounts/{account['id']}", json={"include_in_balance": False})

    assert response.status_code == 200
    assert response.json()["include_in_balance"] is False
    assert client.patch(f"{API}/accounts/{account['id']}", json={"include_in_balance": None}).status_code == 422


def test_an_account_can_be_created_outside_the_balance(client):
    account = create_account(client, include_in_balance=False)

    assert account["include_in_balance"] is False
