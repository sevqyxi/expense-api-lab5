"""Тести POST /rpc (JSON-RPC 2.0) з реальною БД і фейковим AuthService."""
import json
from decimal import Decimal


def create_global_category(client, admin, name="Food"):
    response = client.post("/category/global", headers=admin["headers"], json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def rpc_call(id_, category_id, amount=100.0, user_id=None):
    params = {"category_id": category_id, "amount": amount}
    if user_id is not None:
        params["user_id"] = user_id
    return {"jsonrpc": "2.0", "method": "create_record", "params": params, "id": id_}


def post_rpc(client, payload, headers=None):
    return client.post("/rpc", headers=headers or {}, content=json.dumps(payload))


def test_single_request_creates_record(client, user, admin):
    category_id = create_global_category(client, admin)
    response = post_rpc(client, rpc_call(1, category_id), user["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["jsonrpc"] == "2.0" and body["id"] == 1
    assert body["result"]["status"] == "created"
    record_id = body["result"]["record_id"]
    # JSON-RPC і REST використовують одну й ту саму логіку: запис видно через GET /record
    record = client.get(f"/record/{record_id}", headers=user["headers"]).json()
    assert record["user_id"] == user["id"]
    assert Decimal(str(record["amount"])) == Decimal("100.00")


def test_batch_request_returns_results_in_order(client, user, admin):
    category_id = create_global_category(client, admin)
    batch = [rpc_call(1, category_id, 100.0), rpc_call(2, category_id, 45.5)]
    response = post_rpc(client, batch, user["headers"])
    assert response.status_code == 200
    results = response.json()
    assert [item["id"] for item in results] == [1, 2]
    assert all(item["result"]["status"] == "created" for item in results)
    assert results[0]["result"]["record_id"] != results[1]["result"]["record_id"]


def test_batch_with_failing_item_returns_error_for_that_item_only(client, user, admin):
    category_id = create_global_category(client, admin)
    batch = [rpc_call(1, category_id, 10), rpc_call(2, 999999, 10)]
    results = post_rpc(client, batch, user["headers"]).json()
    assert "result" in results[0]
    assert results[1]["error"]["code"] == -32004
    assert results[1]["id"] == 2


def test_notification_gets_no_response_but_creates_record(client, user, admin):
    category_id = create_global_category(client, admin)
    notification = {"jsonrpc": "2.0", "method": "create_record", "params": {"category_id": category_id, "amount": 5}}
    response = post_rpc(client, notification, user["headers"])
    assert response.status_code == 204
    assert response.content == b""
    assert len(client.get(f"/record?user_id={user['id']}", headers=user["headers"]).json()) == 1


def test_batch_of_notifications_returns_no_content(client, user, admin):
    category_id = create_global_category(client, admin)
    batch = [{"jsonrpc": "2.0", "method": "create_record", "params": {"category_id": category_id, "amount": 5}}]
    assert post_rpc(client, batch, user["headers"]).status_code == 204


def test_empty_batch_is_invalid_request(client, user):
    body = post_rpc(client, [], user["headers"]).json()
    assert body["error"]["code"] == -32600
    assert body["id"] is None


def test_invalid_json_returns_parse_error(client, user):
    response = client.post("/rpc", headers=user["headers"], content=b"{not json")
    assert response.json()["error"]["code"] == -32700
    assert response.json()["id"] is None


def test_object_without_jsonrpc_field_is_invalid_request(client, user):
    body = post_rpc(client, {"foo": "boo"}, user["headers"]).json()
    assert body["error"]["code"] == -32600


def test_unknown_method_returns_method_not_found(client, user):
    payload = {"jsonrpc": "2.0", "method": "delete_everything", "params": {}, "id": 7}
    body = post_rpc(client, payload, user["headers"]).json()
    assert body["error"]["code"] == -32601
    assert body["id"] == 7


def test_invalid_params_return_invalid_params_error(client, user, admin):
    category_id = create_global_category(client, admin)
    body = post_rpc(client, rpc_call(3, category_id, amount=-5), user["headers"]).json()
    assert body["error"]["code"] == -32602
    assert body["id"] == 3


def test_missing_token_returns_401(client, admin):
    category_id = create_global_category(client, admin)
    response = post_rpc(client, rpc_call(1, category_id))
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == -32001


def test_invalid_token_returns_401(client, admin):
    category_id = create_global_category(client, admin)
    response = post_rpc(client, rpc_call(1, category_id), {"Authorization": "Bearer broken.token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == -32001


def test_auditor_gets_forbidden_for_create_record(client, auditor, admin):
    category_id = create_global_category(client, admin)
    body = post_rpc(client, rpc_call(1, category_id), auditor["headers"]).json()
    assert body["error"]["code"] == -32003
    assert body["id"] == 1


def test_user_cannot_create_record_for_other_user(client, user, other_user, admin):
    category_id = create_global_category(client, admin)
    body = post_rpc(client, rpc_call(1, category_id, user_id=other_user["id"]), user["headers"]).json()
    assert body["error"]["code"] == -32004


def test_admin_can_create_record_for_user_through_rpc(client, user, admin):
    category_id = create_global_category(client, admin)
    body = post_rpc(client, rpc_call(1, category_id, user_id=user["id"]), admin["headers"]).json()
    assert body["result"]["status"] == "created"
    record = client.get(f"/record/{body['result']['record_id']}", headers=admin["headers"]).json()
    assert record["user_id"] == user["id"]
