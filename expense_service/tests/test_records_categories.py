"""Тести RBAC, варіанта 2 (персональні та глобальні категорії) і перевірки користувачів через gRPC."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas import RecordCreate


def create_global_category(client, admin, name="Food"):
    response = client.post("/category/global", headers=admin["headers"], json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def create_personal_category(client, owner, name="Hobby"):
    response = client.post("/category", headers=owner["headers"], json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def create_record(client, owner, category_id, amount=100):
    response = client.post("/record", headers=owner["headers"], json={"category_id": category_id, "amount": amount})
    assert response.status_code == 201
    return response.json()["id"]


# user

def test_user_creates_and_reads_own_record(client, user, admin):
    category_id = create_global_category(client, admin)
    response = client.post("/record", headers=user["headers"], json={"category_id": category_id, "amount": "250.50"})
    assert response.status_code == 201
    record = response.json()
    # власник визначається з токена
    assert record["user_id"] == user["id"]
    assert Decimal(str(record["amount"])) == Decimal("250.50")
    assert client.get(f"/record/{record['id']}", headers=user["headers"]).status_code == 200


def test_user_cannot_spoof_user_id(client, user, other_user, admin):
    category_id = create_global_category(client, admin)
    response = client.post(
        "/record", headers=user["headers"], json={"user_id": other_user["id"], "category_id": category_id, "amount": 10}
    )
    assert response.status_code == 404
    response = client.post("/category", headers=user["headers"], json={"name": "X", "user_id": other_user["id"]})
    assert response.status_code == 404


def test_user_cannot_access_other_users_record(client, user, other_user, admin):
    category_id = create_global_category(client, admin)
    record_id = create_record(client, other_user, category_id)
    assert client.get(f"/record/{record_id}", headers=user["headers"]).status_code == 404
    assert client.delete(f"/record/{record_id}", headers=user["headers"]).status_code == 404
    # запис не видалено
    assert client.get(f"/record/{record_id}", headers=other_user["headers"]).status_code == 200


def test_user_filters_only_own_records(client, user, other_user, admin):
    category_id = create_global_category(client, admin)
    own_id = create_record(client, user, category_id)
    create_record(client, other_user, category_id)
    response = client.get(f"/record?category_id={category_id}", headers=user["headers"])
    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [own_id]
    assert client.get(f"/record?user_id={other_user['id']}", headers=user["headers"]).status_code == 404


def test_user_can_delete_own_record(client, user, admin):
    record_id = create_record(client, user, create_global_category(client, admin))
    assert client.delete(f"/record/{record_id}", headers=user["headers"]).status_code == 204
    assert client.get(f"/record/{record_id}", headers=user["headers"]).status_code == 404


def test_filter_without_params_returns_400(client, user):
    response = client.get("/record", headers=user["headers"])
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


# категорії (варіант 2)

def test_user_sees_global_and_own_categories_only(client, user, other_user, admin):
    global_id = create_global_category(client, admin)
    own_id = create_personal_category(client, user)
    other_id = create_personal_category(client, other_user)
    response = client.get("/category", headers=user["headers"])
    ids = [c["id"] for c in response.json()]
    assert global_id in ids and own_id in ids and other_id not in ids
    assert client.get(f"/category/{other_id}", headers=user["headers"]).status_code == 404


def test_personal_category_belongs_to_creator(client, user):
    response = client.post("/category", headers=user["headers"], json={"name": "Hobby"})
    assert response.status_code == 201
    assert response.json()["user_id"] == user["id"]


def test_user_cannot_use_other_users_personal_category(client, user, other_user):
    other_id = create_personal_category(client, other_user)
    response = client.post("/record", headers=user["headers"], json={"category_id": other_id, "amount": 10})
    assert response.status_code == 404


def test_user_can_use_own_personal_category(client, user):
    own_id = create_personal_category(client, user)
    response = client.post("/record", headers=user["headers"], json={"category_id": own_id, "amount": 10})
    assert response.status_code == 201


def test_user_cannot_delete_global_category(client, user, admin):
    global_id = create_global_category(client, admin)
    assert client.delete(f"/category/{global_id}", headers=user["headers"]).status_code == 403


def test_user_can_delete_own_personal_category(client, user):
    own_id = create_personal_category(client, user)
    assert client.delete(f"/category/{own_id}", headers=user["headers"]).status_code == 204


def test_admin_cannot_mix_category_of_another_owner(client, user, other_user, admin):
    other_id = create_personal_category(client, other_user)
    response = client.post(
        "/record", headers=admin["headers"], json={"user_id": user["id"], "category_id": other_id, "amount": 10}
    )
    assert response.status_code == 403


# перевірка існування користувача через gRPC

def test_admin_cannot_create_record_for_unknown_user(client, admin):
    category_id = create_global_category(client, admin)
    response = client.post(
        "/record", headers=admin["headers"], json={"user_id": 999, "category_id": category_id, "amount": 10}
    )
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_auditor_gets_404_for_unknown_user_categories(client, auditor):
    response = client.get("/category?user_id=999", headers=auditor["headers"])
    assert response.status_code == 404


# auditor

def test_auditor_can_read_everything(client, user, auditor, admin):
    category_id = create_global_category(client, admin)
    personal_id = create_personal_category(client, user)
    record_id = create_record(client, user, category_id)
    assert client.get(f"/record/{record_id}", headers=auditor["headers"]).status_code == 200
    assert client.get(f"/category/{personal_id}", headers=auditor["headers"]).status_code == 200
    response = client.get(f"/record?user_id={user['id']}", headers=auditor["headers"])
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_auditor_cannot_write(client, user, auditor, admin):
    category_id = create_global_category(client, admin)
    record_id = create_record(client, user, category_id)
    headers = auditor["headers"]
    assert client.post("/record", headers=headers, json={"category_id": category_id, "amount": 10}).status_code == 403
    assert client.delete(f"/record/{record_id}", headers=headers).status_code == 403
    assert client.post("/category", headers=headers, json={"name": "X"}).status_code == 403
    assert client.post("/category/global", headers=headers, json={"name": "X"}).status_code == 403
    assert client.delete(f"/category/{category_id}", headers=headers).status_code == 403


# admin

def test_admin_has_full_access(client, user, admin):
    category_id = create_global_category(client, admin)
    response = client.post(
        "/record", headers=admin["headers"], json={"user_id": user["id"], "category_id": category_id, "amount": 10}
    )
    assert response.status_code == 201
    record_id = response.json()["id"]
    assert client.delete(f"/record/{record_id}", headers=admin["headers"]).status_code == 204
    assert client.delete(f"/category/{category_id}", headers=admin["headers"]).status_code == 204


# схеми

@pytest.mark.parametrize("amount", [-5, 0, "abc", 10.123, 10_000_000_000])
def test_record_schema_rejects_invalid_amount(amount):
    with pytest.raises(ValidationError):
        RecordCreate(category_id=1, amount=amount)
