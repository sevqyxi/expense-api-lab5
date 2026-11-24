import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from errors import ApiError
from models import UserModel

JWT_ALGORITHM = "HS256"

bearer_scheme = HTTPBearer(auto_error=False)


class TokenError(Exception):
    def __init__(self, message: str):
        self.message = message


def hash_password(password: str) -> str:
    # Argon2id з рекомендованими параметрами RFC 9106 (64 МіБ пам'яті, 3 ітерації),
    # для кожного пароля генерується своя випадкова сіль
    kdf = Argon2id(salt=os.urandom(16), length=32, iterations=3, lanes=4, memory_cost=64 * 1024)
    return kdf.derive_phc_encoded(password.encode())


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    if not password_hash:
        return False
    try:
        Argon2id.verify_phc_encoded(password.encode(), password_hash)
        return True
    except (InvalidKey, ValueError):
        return False


def get_jwt_secret() -> str:
    # секрет береться лише зі змінної оточення, у коді його немає
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY environment variable is not set")
    return secret


def get_token_lifetime() -> timedelta:
    return timedelta(minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "60")))


def create_access_token(user: UserModel, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "roles": [user.role],
        "iat": now,
        "exp": now + (expires_delta if expires_delta is not None else get_token_lifetime()),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "exp"]},
    )


def user_from_token(db: Session, token: str) -> UserModel:
    # перевірка JWT і того, що користувач з токена ще існує
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise TokenError("Access token has expired")
    except (jwt.InvalidTokenError, ValueError):
        raise TokenError("Invalid access token")

    user = db.get(UserModel, user_id)
    if user is None:
        raise TokenError("User from token no longer exists")
    return user


def unauthorized(message: str) -> ApiError:
    return ApiError(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserModel:
    # користувач визначається тільки за перевіреним JWT із заголовка Authorization
    if credentials is None:
        raise unauthorized("Missing access token")
    try:
        return user_from_token(db, credentials.credentials)
    except TokenError as error:
        raise unauthorized(error.message)


def require_roles(*roles: str):
    # RBAC: роль береться з БД, тому зміна ролі адміністратором діє одразу
    def checker(user: UserModel = Depends(get_current_user)) -> UserModel:
        if user.role not in roles:
            raise ApiError(403, "forbidden", "Access denied: insufficient privileges")
        return user

    return checker
