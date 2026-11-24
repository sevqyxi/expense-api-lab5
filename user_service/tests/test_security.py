"""Модульні тести: хешування паролів Argon2id, JWT і Pydantic-схеми (без БД)."""
from datetime import timedelta
from types import SimpleNamespace

import jwt
import pytest
from pydantic import ValidationError

from schemas import RegisterIn
from security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_is_argon2id():
    password_hash = hash_password("Secret12345")
    assert password_hash.startswith("$argon2id$")
    assert "Secret12345" not in password_hash


def test_same_password_gives_different_hashes():
    # кожен хеш має власну випадкову сіль
    assert hash_password("Secret12345") != hash_password("Secret12345")


def test_verify_password():
    password_hash = hash_password("Secret12345")
    assert verify_password("Secret12345", password_hash) is True
    assert verify_password("WrongPass1", password_hash) is False


def test_verify_password_with_empty_or_broken_hash():
    assert verify_password("Secret12345", None) is False
    assert verify_password("Secret12345", "not-a-hash") is False


def test_access_token_contains_user_id_role_and_expiration():
    token = create_access_token(SimpleNamespace(id=7, role="auditor"))
    payload = decode_access_token(token)
    assert payload["sub"] == "7"
    assert payload["roles"] == ["auditor"]
    assert payload["exp"] > payload["iat"]


def test_expired_token_is_rejected():
    token = create_access_token(SimpleNamespace(id=1, role="user"), expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_other_secret_is_rejected():
    token = jwt.encode(
        {"sub": "1", "roles": ["admin"], "exp": 9999999999},
        "another-secret-key-that-is-long-enough-123",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_register_schema_forbids_role_field():
    with pytest.raises(ValidationError):
        RegisterIn(username="hacker", password="Secret12345", role="admin")


@pytest.mark.parametrize(
    "data",
    [
        {"username": "ab", "password": "Secret12345"},
        {"username": "bad name!", "password": "Secret12345"},
        {"username": "alice", "password": "short"},
        {"username": "alice"},
    ],
)
def test_register_schema_rejects_invalid_data(data):
    with pytest.raises(ValidationError):
        RegisterIn(**data)
