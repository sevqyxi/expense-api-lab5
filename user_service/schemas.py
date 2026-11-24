from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# Вхідні дані (тіла POST/PATCH-запитів)

class RegisterIn(BaseModel):
    # extra="forbid": поле role у тілі реєстрації дає 400, роль обрати не можна
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "auditor", "admin"]


# Вихідні DTO (відповіді API). Пароль і його хеш у відповіді не потрапляють

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: Optional[str]
    name: str
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
