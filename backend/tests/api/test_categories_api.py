import uuid

from tests.api.helpers import API, create_account, create_category, create_transaction, error_code


def test_create_and_list_categories_by_type(client):
    food = create_category(client, "Food", "expense", icon="utensils", color="#FF8800")
    salary = create_category(client, "Salary", "income")

    all_ids = {item["id"] for item in client.get(f"{API}/categories").json()}
    expenses = {item["id"] for item in client.get(f"{API}/categories?type=expense").json()}

    assert {food["id"], salary["id"]} <= all_ids
    assert food["id"] in expenses
    assert salary["id"] not in expenses
    assert food["color"] == "#FF8800"


def test_subcategory_must_match_the_type_of_its_parent(client):
    food = create_category(client, "Food", "expense")

    ok = client.post(f"{API}/categories", json={"name": "Groceries", "type": "expense", "parent_id": food["id"]})
    assert ok.status_code == 201
    assert ok.json()["parent_id"] == food["id"]

    wrong_type = client.post(f"{API}/categories", json={"name": "Bonus", "type": "income", "parent_id": food["id"]})
    assert wrong_type.status_code == 422
    assert error_code(wrong_type) == "category_type_mismatch"


def test_there_are_only_two_levels(client):
    food = create_category(client, "Food", "expense")
    groceries = create_category(client, "Groceries", "expense", parent_id=food["id"])

    response = client.post(
        f"{API}/categories", json={"name": "Fruit", "type": "expense", "parent_id": groceries["id"]}
    )

    assert response.status_code == 422
    assert error_code(response) == "invalid_parent"


def test_missing_parent_is_rejected(client):
    response = client.post(
        f"{API}/categories", json={"name": "Orphan", "type": "expense", "parent_id": str(uuid.uuid4())}
    )

    assert response.status_code == 422
    assert error_code(response) == "parent_not_found"


def test_names_are_unique_per_level_ignoring_case(client):
    food = create_category(client, "Food", "expense")

    duplicate = client.post(f"{API}/categories", json={"name": "FOOD", "type": "expense"})
    assert duplicate.status_code == 409
    assert error_code(duplicate) == "category_exists"

    # The same name is fine under another parent, or in another type.
    assert client.post(f"{API}/categories", json={"name": "Food", "type": "income"}).status_code == 201
    other = create_category(client, "Home", "expense")
    for parent in (food, other):
        created = client.post(
            f"{API}/categories", json={"name": "Misc", "type": "expense", "parent_id": parent["id"]}
        )
        assert created.status_code == 201


def test_update_name_and_color_but_not_type(client):
    category = create_category(client, "Food", "expense")

    updated = client.patch(f"{API}/categories/{category['id']}", json={"name": "Eating out", "color": "#00AAFF"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Eating out"
    assert updated.json()["color"] == "#00AAFF"

    assert client.patch(f"{API}/categories/{category['id']}", json={"type": "income"}).status_code == 422
    assert client.patch(f"{API}/categories/{category['id']}", json={"color": "orange"}).status_code == 422
    assert client.patch(f"{API}/categories/{category['id']}", json={"name": None}).status_code == 422


def test_a_category_can_be_moved_under_another_but_not_under_itself(client):
    food = create_category(client, "Food", "expense")
    snacks = create_category(client, "Snacks", "expense")

    moved = client.patch(f"{API}/categories/{snacks['id']}", json={"parent_id": food["id"]})
    assert moved.status_code == 200
    assert moved.json()["parent_id"] == food["id"]

    itself = client.patch(f"{API}/categories/{food['id']}", json={"parent_id": food["id"]})
    assert itself.status_code == 422
    assert error_code(itself) == "invalid_parent"

    # Food now has a child, so it cannot become a child itself.
    other = create_category(client, "Other", "expense")
    blocked = client.patch(f"{API}/categories/{food['id']}", json={"parent_id": other["id"]})
    assert blocked.status_code == 422


def test_unused_category_is_deleted(client):
    category = create_category(client)

    assert client.delete(f"{API}/categories/{category['id']}").status_code == 204

    remaining = {item["id"] for item in client.get(f"{API}/categories").json()}
    assert category["id"] not in remaining
    assert client.delete(f"{API}/categories/{category['id']}").status_code == 404


def test_category_with_subcategories_cannot_be_deleted(client):
    food = create_category(client, "Food", "expense")
    create_category(client, "Groceries", "expense", parent_id=food["id"])

    response = client.delete(f"{API}/categories/{food['id']}")

    assert response.status_code == 409
    assert error_code(response) == "category_has_children"


def test_category_in_use_needs_a_destination_for_its_movements(client):
    bank = create_account(client)
    food = create_category(client, "Food", "expense")
    eating_out = create_category(client, "Eating out", "expense")
    movement = create_transaction(client, bank, "expense", 50, category_id=food["id"])

    refused = client.delete(f"{API}/categories/{food['id']}")
    assert refused.status_code == 409
    assert error_code(refused) == "category_in_use"
    assert refused.json()["error"]["details"] == {"transactions": 1}

    wrong_type = create_category(client, "Salary", "income")
    mismatch = client.delete(f"{API}/categories/{food['id']}?reassign_to={wrong_type['id']}")
    assert mismatch.status_code == 422
    assert error_code(mismatch) == "category_type_mismatch"

    itself = client.delete(f"{API}/categories/{food['id']}?reassign_to={food['id']}")
    assert itself.status_code == 422

    moved = client.delete(f"{API}/categories/{food['id']}?reassign_to={eating_out['id']}")
    assert moved.status_code == 204
    assert client.get(f"{API}/transactions/{movement['id']}").json()["category_id"] == eating_out["id"]
