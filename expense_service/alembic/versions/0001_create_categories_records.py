"""create categories and records tables (Expense Service)

Revision ID: 0001
Revises:
Create Date: 2026-11-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL — глобальна категорія, інакше — персональна.
    # user_id тут без зовнішнього ключа: користувачі лежать в БД User Service
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])

    op.create_table(
        "records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_records_amount_positive"),
    )
    op.create_index("ix_records_user_id", "records", ["user_id"])
    op.create_index("ix_records_category_id", "records", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_records_category_id", table_name="records")
    op.drop_index("ix_records_user_id", table_name="records")
    op.drop_table("records")
    op.drop_index("ix_categories_user_id", table_name="categories")
    op.drop_table("categories")
