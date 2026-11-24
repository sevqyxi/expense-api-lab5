"""Чисті тести протоколу JSON-RPC 2.0 (без БД і без gRPC)."""
from errors import ApiError
from jsonrpc import (
    FORBIDDEN,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    NOT_FOUND,
    RpcError,
    handle_payload,
)


def dispatch(method, params):
    if method == "echo":
        return params
    if method == "forbidden":
        raise ApiError(403, "forbidden", "no access")
    if method == "missing":
        raise ApiError(404, "not_found", "nothing here")
    if method == "bad_params":
        raise RpcError(INVALID_PARAMS, "bad")
    if method == "crash":
        raise RuntimeError("secret internal detail")
    raise RpcError(METHOD_NOT_FOUND, "Method not found")


def test_single_request_result():
    response = handle_payload({"jsonrpc": "2.0", "method": "echo", "params": {"a": 1}, "id": "abc"}, dispatch)
    assert response == {"jsonrpc": "2.0", "result": {"a": 1}, "id": "abc"}


def test_request_without_params_gets_empty_object():
    response = handle_payload({"jsonrpc": "2.0", "method": "echo", "id": 5}, dispatch)
    assert response["result"] == {}


def test_notification_returns_none():
    assert handle_payload({"jsonrpc": "2.0", "method": "echo", "params": {}}, dispatch) is None


def test_null_id_is_a_normal_request():
    response = handle_payload({"jsonrpc": "2.0", "method": "echo", "id": None}, dispatch)
    assert response["id"] is None and "result" in response


def test_api_error_codes_are_mapped():
    assert handle_payload({"jsonrpc": "2.0", "method": "forbidden", "id": 1}, dispatch)["error"]["code"] == FORBIDDEN
    assert handle_payload({"jsonrpc": "2.0", "method": "missing", "id": 2}, dispatch)["error"]["code"] == NOT_FOUND
    assert handle_payload({"jsonrpc": "2.0", "method": "bad_params", "id": 3}, dispatch)["error"]["code"] == INVALID_PARAMS


def test_unexpected_error_hides_details():
    response = handle_payload({"jsonrpc": "2.0", "method": "crash", "id": 4}, dispatch)
    assert response["error"] == {"code": INTERNAL_ERROR, "message": "Internal error"}


def test_unknown_method():
    response = handle_payload({"jsonrpc": "2.0", "method": "nope", "id": 9}, dispatch)
    assert response["error"]["code"] == METHOD_NOT_FOUND
    assert response["id"] == 9


def test_wrong_version_is_invalid_request():
    response = handle_payload({"jsonrpc": "1.0", "method": "echo", "id": 1}, dispatch)
    assert response["error"]["code"] == INVALID_REQUEST
    assert response["id"] == 1


def test_non_object_item_is_invalid_request():
    response = handle_payload(42, dispatch)
    assert response == {"jsonrpc": "2.0", "error": {"code": INVALID_REQUEST, "message": "Invalid Request"}, "id": None}


def test_object_id_is_invalid_request():
    response = handle_payload({"jsonrpc": "2.0", "method": "echo", "id": [1]}, dispatch)
    assert response["error"]["code"] == INVALID_REQUEST
    assert response["id"] is None


def test_boolean_id_is_invalid_request():
    response = handle_payload({"jsonrpc": "2.0", "method": "echo", "id": True}, dispatch)
    assert response["error"]["code"] == INVALID_REQUEST


def test_string_params_are_invalid_request():
    response = handle_payload({"jsonrpc": "2.0", "method": "echo", "params": "x", "id": 1}, dispatch)
    assert response["error"]["code"] == INVALID_REQUEST


def test_empty_batch_is_invalid_request():
    response = handle_payload([], dispatch)
    assert response["error"]["code"] == INVALID_REQUEST


def test_batch_keeps_order_and_skips_notifications():
    batch = [
        {"jsonrpc": "2.0", "method": "echo", "params": {"n": 1}, "id": 1},
        {"jsonrpc": "2.0", "method": "echo", "params": {"n": 2}},
        {"jsonrpc": "2.0", "method": "missing", "id": 3},
    ]
    responses = handle_payload(batch, dispatch)
    assert [item["id"] for item in responses] == [1, 3]
    assert responses[0]["result"] == {"n": 1}
    assert responses[1]["error"]["code"] == NOT_FOUND


def test_batch_with_invalid_item_still_answers_others():
    batch = [{"jsonrpc": "2.0", "method": "echo", "id": 1}, "garbage"]
    responses = handle_payload(batch, dispatch)
    assert len(responses) == 2
    assert responses[1]["error"]["code"] == INVALID_REQUEST


def test_batch_of_notifications_returns_none():
    batch = [{"jsonrpc": "2.0", "method": "echo", "params": {}}]
    assert handle_payload(batch, dispatch) is None
