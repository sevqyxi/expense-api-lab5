"""Інтеграційні тести реєстрації, входу, JWT і healthcheck User Service (з тестовою БД)."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import main
from database import SessionLocal
from models import UserModel
from security import create_access_token, decode_access_token


def test_liveness_timestamp(client):
    response = client.get("/healthz/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


@pytest.mark.freeze_time("2026-10-05 12:00:00")
def test_frozen_time_check(client):
    response = client.get("/healthz/live")
    assert response.json()["timestamp"].startswith("2026-10-05T12:00:00")


def test_readiness_ok(client):
    response = client.get("/healthz/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_when_database_unavailable(client, monkeypatch):
    monkeypatch.setattr(main, "database_is_available", lambda: False)
    response = client.get("/healthz/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_register_creates_user_with_role_user(client):
    response = client.post("/register", json={"username": "alice", "password": "Secret12345", "name": "Alice"})
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "alice"
    assert body["role"] == "user"
    # пароль і хеш ніколи не повертаються
    assert "password" not in body and "password_hash" not in body


def test_register_stores_argon2id_hash(client):
    client.post("/register", json={"username": "alice", "password": "Secret12345"})
    with SessionLocal() as db:
        user = db.scalar(select(UserModel).where(UserModel.username == "alice"))
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != "Secret12345"


def test_register_cannot_choose_admin_role(client):
    response = client.post("/register", json={"username": "hacker", "password": "Secret12345", "role": "admin"})
    assert response.status_code == 400


def test_register_duplicate_username(client):
    client.post("/register", json={"username": "alice", "password": "Secret12345"})
    response = client.post("/register", json={"username": "alice", "password": "Other12345"})
    assert response.status_code == 409


def test_register_invalid_data(client):
    response = client.post("/register", json={"username": "a", "password": "123"})
    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_login_returns_jwt(client):
    client.post("/register", json={"username": "alice", "password": "Secret12345"})
    response = client.post("/login", json={"username": "alice", "password": "Secret12345"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = decode_access_token(body["access_token"])
    assert payload["roles"] == ["user"]
    assert "exp" in payload and "sub" in payload


def test_login_wrong_password(client):
    client.post("/register", json={"username": "alice", "password": "Secret12345"})
    response = client.post("/login", json={"username": "alice", "password": "WrongPass1"})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_login_unknown_user(client):
    response = client.post("/login", json={"username": "nobody", "password": "Secret12345"})
    assert response.status_code == 401


def test_protected_route_without_token(client):
    response = client.get("/users")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_route_with_invalid_token(client):
    response = client.get("/users", headers={"Authorization": "Bearer not.a.valid.token"})
    assert response.status_code == 401


def test_protected_route_with_wrong_scheme(client, user):
    token = user["headers"]["Authorization"].split()[1]
    response = client.get("/users", headers={"Authorization": f"Basic {token}"})
    assert response.status_code == 401


def test_protected_route_with_expired_token(client, user):
    token = create_access_token(SimpleNamespace(id=user["id"], role="user"), expires_delta=timedelta(seconds=-1))
    response = client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["message"] == "Access token has expired"


def test_token_of_deleted_user_is_rejected(client, user, admin):
    assert client.delete(f"/user/{user['id']}", headers=admin["headers"]).status_code == 204
    response = client.get(f"/user/{user['id']}", headers=user["headers"])
    assert response.status_code == 401
