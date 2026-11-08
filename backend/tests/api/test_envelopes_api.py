from decimal import Decimal

from tests.api.helpers import (
    API,
    balance_of,
    create_account,
    create_category,
    create_transaction,
    error_code,
    insert_transaction,
)

D = Decimal


def make_envelope(client, account, name="SOAT", **extra) -> dict:
    response = client.post(f"{API}/envelopes", json={"account_id": account["id"], "name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def entry(client, envelope, kind, amount):
    return client.post(f"{API}/envelopes/{envelope['id']}/entries", json={"kind": kind, "amount": str(amount)})


def wealth(client) -> dict:
    return client.get(f"{API}/wealth").json()


def test_new_envelope_is_empty_and_does_not_repeat(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=1_000_000)

    envelope = make_envelope(client, wallet, target_amount="480000", due_date="2099-02-06")

    assert envelope["balance"] == "0.00"
    assert envelope["repeats_yearly"] is False
    assert envelope["account_name"] == "Wallet"


def test_setting_money_apart_lowers_the_balance_of_the_app_but_not_the_account(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=1_000_000)
    envelope = make_envelope(client, wallet)

    assert entry(client, envelope, "contribute", 300_000).status_code == 201

    assert balance_of(client, wallet) == D(1_000_000)
    body = wealth(client)
    assert body["available"] == "700000.00"
    assert body["real_money"] == "700000.00"
    row = next(a for a in body["accounts"] if a["id"] == wallet["id"])
    assert row["balance"] == "1000000.00"
    assert row["reserved"] == "300000.00"
    assert client.get(f"{API}/accounts/{wallet['id']}").json()["reserved"] == "300000.00"


def test_contributing_is_not_an_expense(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    envelope = make_envelope(client, wallet)
    entry(client, envelope, "contribute", 100_000)

    summary = client.get(f"{API}/summary?month=2099-01").status_code
    transactions = client.get(f"{API}/transactions").json()

    assert summary in (200, 422)
    assert transactions["items"] == []


def test_cannot_set_apart_more_than_is_available(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=100_000)
    first = make_envelope(client, wallet, name="A")
    second = make_envelope(client, wallet, name="B")
    entry(client, first, "contribute", 80_000)

    response = entry(client, second, "contribute", 30_000)

    assert response.status_code == 409
    assert error_code(response) == "insufficient_available"
    assert response.json()["error"]["details"]["available"] == "20000.00"


def test_releasing_returns_the_money_and_cannot_exceed_the_envelope(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=100_000)
    envelope = make_envelope(client, wallet)
    entry(client, envelope, "contribute", 60_000)

    too_much = entry(client, envelope, "release", 70_000)
    released = entry(client, envelope, "release", 20_000)

    assert too_much.status_code == 409
    assert error_code(too_much) == "insufficient_envelope"
    assert released.json()["balance"] == "40000.00"
    assert wealth(client)["available"] == "60000.00"


def test_envelopes_only_in_accounts_the_user_spends_from(client):
    card = create_account(client, name="Card", type="credit_card")

    response = client.post(f"{API}/envelopes", json={"account_id": card["id"], "name": "X"})

    assert response.status_code == 422
    assert error_code(response) == "invalid_envelope_account"


def test_balance_falls_back_when_the_account_drops_below_what_is_set_apart(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=100_000)
    envelope = make_envelope(client, wallet)
    entry(client, envelope, "contribute", 100_000)
    create_transaction(client, wallet, "expense", 40_000)

    body = wealth(client)
    listing = client.get(f"{API}/envelopes").json()

    assert body["available"] == "0.00"
    row = next(a for a in body["accounts"] if a["id"] == wallet["id"])
    assert row["reserved"] == "60000.00"
    assert listing["envelopes"][0]["shortfall"] == "40000.00"


def test_paying_with_a_new_expense_records_it_once_and_frees_the_money(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=1_000_000)
    card = create_account(client, name="Card", type="credit_card")
    category = create_category(client, name="Transport")
    envelope = make_envelope(client, wallet, target_amount="300000", due_date="2099-02-06")
    entry(client, envelope, "contribute", 300_000)

    response = client.post(
        f"{API}/envelopes/{envelope['id']}/pay",
        json={"expense": {"account_id": card["id"], "amount": "258041", "category_id": category["id"]}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["freed"] == "258041.00"
    assert body["envelope"]["balance"] == "41959.00"
    expenses = client.get(f"{API}/transactions").json()["items"]
    assert len(expenses) == 1
    assert expenses[0]["type"] == "expense" and expenses[0]["category_id"] == category["id"]
    assert balance_of(client, card) == D(-258_041)
    # The freed money is available again, the rest stays apart, and the card debt shows.
    wealth_body = wealth(client)
    assert wealth_body["available"] == str(D(1_000_000 - 41_959)) + ".00"
    assert wealth_body["credit_card_debt"] == "258041.00"


def test_paying_more_than_the_envelope_holds_takes_the_rest_from_what_is_available(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    envelope = make_envelope(client, wallet)
    entry(client, envelope, "contribute", 100_000)

    response = client.post(
        f"{API}/envelopes/{envelope['id']}/pay",
        json={"expense": {"account_id": wallet["id"], "amount": "150000"}},
    )

    assert response.json()["freed"] == "100000.00"
    assert response.json()["envelope"]["balance"] == "0.00"
    assert wealth(client)["available"] == "350000.00"


def test_paying_a_pending_movement_confirms_it(client, db):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    card = create_account(client, name="Card", type="credit_card")
    envelope = make_envelope(client, wallet)
    entry(client, envelope, "contribute", 200_000)
    pending = insert_transaction(db, card["id"], amount="120000")

    response = client.post(f"{API}/envelopes/{envelope['id']}/pay", json={"transaction_id": pending})

    assert response.status_code == 200, response.text
    assert client.get(f"{API}/transactions/{pending}").json()["status"] == "confirmed"
    assert response.json()["envelope"]["balance"] == "80000.00"
    again = client.post(f"{API}/envelopes/{envelope['id']}/pay", json={"transaction_id": pending})
    assert again.status_code == 409
    assert error_code(again) == "already_paid"


def test_cannot_pay_with_something_that_is_not_an_expense(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    envelope = make_envelope(client, wallet)
    income = create_transaction(client, wallet, "income", 1000)

    response = client.post(f"{API}/envelopes/{envelope['id']}/pay", json={"transaction_id": income["id"]})

    assert response.status_code == 422
    assert error_code(response) == "not_an_expense"


def test_pay_needs_exactly_one_way_to_say_what_is_paid(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    envelope = make_envelope(client, wallet)

    response = client.post(f"{API}/envelopes/{envelope['id']}/pay", json={})

    assert response.status_code == 422


def test_a_yearly_envelope_moves_its_date_a_year_ahead_after_paying(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    yearly = make_envelope(client, wallet, name="Platzi", due_date="2099-03-22", repeats_yearly=True)
    once = make_envelope(client, wallet, name="One-off", due_date="2099-03-22")
    entry(client, yearly, "contribute", 1_000)
    entry(client, once, "contribute", 1_000)

    for envelope in (yearly, once):
        client.post(
            f"{API}/envelopes/{envelope['id']}/pay",
            json={"expense": {"account_id": wallet["id"], "amount": "1000"}},
        )

    dates = {e["name"]: e["due_date"] for e in client.get(f"{API}/envelopes").json()["envelopes"]}
    assert dates == {"Platzi": "2100-03-22", "One-off": "2099-03-22"}


def test_deleting_archives_only_an_empty_envelope(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    envelope = make_envelope(client, wallet)
    entry(client, envelope, "contribute", 1000)

    blocked = client.delete(f"{API}/envelopes/{envelope['id']}")
    entry(client, envelope, "release", 1000)
    done = client.delete(f"{API}/envelopes/{envelope['id']}")

    assert blocked.status_code == 409
    assert error_code(blocked) == "envelope_not_empty"
    assert done.status_code == 204
    assert client.get(f"{API}/envelopes").json()["envelopes"] == []


def test_listing_gives_totals_and_the_suggestion_of_the_month(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=1_000_000)
    envelope = make_envelope(client, wallet, target_amount="400000", due_date="2099-02-06")
    entry(client, envelope, "contribute", 100_000)

    listing = client.get(f"{API}/envelopes").json()

    assert listing["reserved_total"] == "100000.00"
    item = listing["envelopes"][0]
    assert item["ready"] is False
    assert item["suggested_monthly"] is not None
    assert D(listing["suggested_total"]) == D(item["suggested_monthly"])


def test_interest_stays_available(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=1_000_000)
    envelope = make_envelope(client, wallet)
    entry(client, envelope, "contribute", 300_000)
    category = create_category(client, name="Rendimientos", type="income")
    create_transaction(client, wallet, "income", 5_000, category_id=category["id"])

    assert wealth(client)["available"] == "705000.00"


def pay_new(client, envelope, account, amount):
    response = client.post(
        f"{API}/envelopes/{envelope['id']}/pay",
        json={"expense": {"account_id": account["id"], "amount": str(amount)}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_discarding_or_deleting_the_paid_expense_gives_the_money_back_to_the_envelope(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    envelope = make_envelope(client, wallet)
    entry(client, envelope, "contribute", 200_000)

    paid = pay_new(client, envelope, wallet, 150_000)
    assert paid["envelope"]["balance"] == "50000.00"
    client.delete(f"{API}/transactions/{paid['transaction_id']}")

    assert client.get(f"{API}/envelopes").json()["envelopes"][0]["balance"] == "200000.00"


def test_the_amount_of_a_paid_expense_cannot_be_edited(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    envelope = make_envelope(client, wallet)
    entry(client, envelope, "contribute", 200_000)
    paid = pay_new(client, envelope, wallet, 150_000)

    response = client.patch(f"{API}/transactions/{paid['transaction_id']}", json={"amount": "100000"})
    allowed = client.patch(f"{API}/transactions/{paid['transaction_id']}", json={"merchant": "Other"})

    assert response.status_code == 409
    assert error_code(response) == "linked_to_envelope"
    assert allowed.status_code == 200


def test_the_yearly_date_moves_only_when_the_envelope_paid_something(client):
    wallet = create_account(client, name="Wallet", type="wallet", initial=500_000)
    envelope = make_envelope(client, wallet, due_date="2099-03-22", repeats_yearly=True)

    pay_new(client, envelope, wallet, 1_000)

    assert client.get(f"{API}/envelopes").json()["envelopes"][0]["due_date"] == "2099-03-22"
