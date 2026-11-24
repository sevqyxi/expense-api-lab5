from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# максимальне значення для колонки INTEGER у PostgreSQL
MAX_ID = 2_147_483_647
# максимальна сума, яка вміщується в Numeric(12, 2)
MAX_AMOUNT = Decimal("9999999999.99")


# Вхідні дані (тіла POST-запитів)

class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    # власник персональної категорії; вказати іншого користувача може лише admin
    user_id: Optional[int] = Field(default=None, gt=0, le=MAX_ID, strict=True)


class GlobalCategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)


class RecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # не передано — запис створюється для поточного користувача з токена
    user_id: Optional[int] = Field(default=None, gt=0, le=MAX_ID, strict=True)
    category_id: int = Field(gt=0, le=MAX_ID, strict=True)
    amount: Decimal = Field(gt=0, le=MAX_AMOUNT, decimal_places=2)
    created_at: Optional[datetime] = None


# Вихідні DTO (відповіді API), створюються з ORM-об'єктів

class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    user_id: Optional[int]


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category_id: int
    created_at: datetime
    amount: Decimal
