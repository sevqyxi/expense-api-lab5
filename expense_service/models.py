from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class CategoryModel(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # NULL — глобальна категорія, інакше — персональна категорія користувача.
    # Це просто число: користувачі лежать в іншій БД, зовнішнього ключа немає
    user_id: Mapped[Optional[int]] = mapped_column(index=True)

    records: Mapped[List["RecordModel"]] = relationship(
        back_populates="category", cascade="all, delete-orphan", passive_deletes=True
    )


class RecordModel(Base):
    __tablename__ = "records"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_records_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # ідентифікатор користувача з User Service, без зовнішнього ключа
    user_id: Mapped[int] = mapped_column(index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # гроші зберігаються як Numeric(12, 2), а не float
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    category: Mapped["CategoryModel"] = relationship(back_populates="records")
