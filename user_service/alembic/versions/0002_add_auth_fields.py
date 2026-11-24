"""add username, password_hash and role to users (JWT + RBAC)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Старі користувачі з ЛР3 не мають логіна й пароля, тому ці поля nullable:
    # такі користувачі отримують роль user, зберігають свої дані, але увійти не можуть
    op.add_column("users", sa.Column("username", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
    )
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_check_constraint("ck_users_role", "users", "role IN ('user', 'auditor', 'admin')")


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
