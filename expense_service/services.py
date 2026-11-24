from sqlalchemy.orm import Session

import auth
from auth import ROLE_USER, ROLE_ADMIN, CurrentUser
from errors import ApiError
from models import CategoryModel, RecordModel
from schemas import MAX_ID, RecordCreate


def not_found(name: str, obj_id) -> ApiError:
    return ApiError(404, "not_found", f"{name} with id {obj_id} not found")


def get_or_404(db: Session, model, obj_id: int, name: str):
    obj = db.get(model, obj_id) if 0 < obj_id <= MAX_ID else None
    if obj is None:
        raise not_found(name, obj_id)
    return obj


def is_user(current: CurrentUser) -> bool:
    return current.role == ROLE_USER


def check_own_user_id(current: CurrentUser, user_id):
    # звичайний user не може підставити чужий user_id: для нього чужих даних "не існує"
    if is_user(current) and user_id is not None and user_id != current.id:
        raise not_found("User", user_id)


def ensure_user_exists(current: CurrentUser, user_id: int):
    # користувачі лежать в іншій БД, тому перевіряємо їх через gRPC до User Service
    if user_id == current.id:
        return
    if not (0 < user_id <= MAX_ID) or not auth.user_exists(current, user_id):
        raise not_found("User", user_id)


def get_visible_category(db: Session, current: CurrentUser, category_id: int) -> CategoryModel:
    category = get_or_404(db, CategoryModel, category_id, "Category")
    # user бачить лише глобальні та власні персональні категорії
    if is_user(current) and category.user_id is not None and category.user_id != current.id:
        raise not_found("Category", category_id)
    return category


def get_visible_record(db: Session, current: CurrentUser, record_id: int) -> RecordModel:
    record = get_or_404(db, RecordModel, record_id, "Record")
    if is_user(current) and record.user_id != current.id:
        raise not_found("Record", record_id)
    return record


def create_record(db: Session, current: CurrentUser, data: RecordCreate) -> RecordModel:
    # Створювати витрати можуть лише user та admin
    if current.role not in (ROLE_USER, ROLE_ADMIN):
        raise ApiError(403, "forbidden", "Access denied: insufficient privileges")

    # спільна логіка для REST (POST /record) і JSON-RPC (create_record)
    check_own_user_id(current, data.user_id)
    owner_id = data.user_id if data.user_id is not None else current.id
    ensure_user_exists(current, owner_id)
    category = get_visible_category(db, current, data.category_id)

    # варіант 2: персональна категорія має належати власнику витрати
    if category.user_id is not None and category.user_id != owner_id:
        raise ApiError(
            403, "forbidden", f"Category with id {category.id} is a personal category of another user"
        )

    record = RecordModel(
        user_id=owner_id,
        category_id=category.id,
        amount=data.amount,
        **({"created_at": data.created_at} if data.created_at else {}),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
