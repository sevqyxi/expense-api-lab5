"""Тести відмов міжсервісної взаємодії (User Service недоступний, поганий токен) і healthcheck."""
import grpc

import auth
from proto import auth_pb2_grpc


def dead_user_service_stub():
    # порт без сервера: виклик має завершитися помилкою UNAVAILABLE
    channel = grpc.insecure_channel("localhost:1")
    return auth_pb2_grpc.AuthServiceStub(channel)


def test_liveness(client):
    response = client.get("/healthz/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness(client):
    response = client.get("/healthz/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_user_service_unavailable_returns_503_for_rest(client, user, monkeypatch):
    monkeypatch.setattr(auth, "_stub", dead_user_service_stub())
    response = client.get("/category", headers=user["headers"])
    assert response.status_code == 503
    assert response.json()["error"] == "service_unavailable"


def test_user_service_unavailable_returns_503_for_rpc(client, user, monkeypatch):
    monkeypatch.setattr(auth, "_stub", dead_user_service_stub())
    payload = {"jsonrpc": "2.0", "method": "create_record", "params": {"category_id": 1, "amount": 10}, "id": 1}
    response = client.post("/rpc", headers=user["headers"], json=payload)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == -32002


def test_request_without_token_is_401(client):
    response = client.get("/record?user_id=1")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_is_401_with_message(client):
    response = client.get("/record/1", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401
    assert response.json()["message"] == "Invalid access token"
