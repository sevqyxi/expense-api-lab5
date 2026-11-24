from typing import Optional

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

ROLE_USER = "user"
ROLE_AUDITOR = "auditor"
ROLE_ADMIN = "admin"
ROLES = (ROLE_USER, ROLE_AUDITOR, ROLE_ADMIN)


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'auditor', 'admin')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # у старих користувачів з ЛР3 username і password_hash порожні — увійти вони не можуть
    username: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_USER, server_default=ROLE_USER)
