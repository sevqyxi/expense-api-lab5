import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_USER,
    CurrentUser,
    bearer_token,
    get_current_user,
    require_roles,
    resolve_current_user,
)
from database import SessionLocal, database_is_available, get_db, run_migrations
from errors import ApiError
from jsonrpc import (
    API_ERROR_CODES,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    UNAUTHORIZED,
    RpcError,
    error_response,
    handle_payload,
    parse_error_response,
)
from models import CategoryModel, RecordModel
from schemas import CategoryCreate, CategoryOut, GlobalCategoryCreate, RecordCreate, RecordOut
from services import (
    check_own_user_id,
    create_record,
    ensure_user_exists,
    get_visible_category,
    get_visible_record,
    is_user,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    yield


app = FastAPI(title="Expense Service", lifespan=lifespan)

# залежності для перевірки ролей
any_role = Depends(get_current_user)
readers = Depends(require_roles(ROLE_AUDITOR, ROLE_ADMIN))
writers = Depends(require_roles(ROLE_USER, ROLE_ADMIN))
admin_only = Depends(require_roles(ROLE_ADMIN))


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "message": exc.message},
        headers=exc.headers,
    )


# Некоректні дані (тіло, query, path, невалідний JSON) -> 400 замість стандартного 422
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    parts = []
    for err in exc.errors():
        field = ".".join(str(x) for x in err["loc"] if x not in ("body", "query", "path"))
        parts.append(f"{field}: {err['msg']}" if field else err["msg"])
    return JSONResponse(status_code=400, content={"error": "validation_error", "message": "; ".join(parts)})


# Системні маршрути (публічні)

@app.get("/healthz/live")
def healthz_live():
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/healthz/ready")
def healthz_ready():
    if not database_is_available():
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})
    return {"status": "ready", "database": "ok"}


# Categories

@app.get("/category", response_model=List[CategoryOut])
def get_categories(
    user_id: Optional[int] = None, current: CurrentUser = any_role, db: Session = Depends(get_db)
):
    query = select(CategoryModel).order_by(CategoryModel.id)
    if is_user(current):
        # user: глобальні + власні персональні категорії
        check_own_user_id(current, user_id)
        query = query.where(or_(CategoryModel.user_id.is_(None), CategoryModel.user_id == current.id))
    elif user_id is not None:
        # auditor/admin: глобальні + персональні категорії вибраного користувача
        ensure_user_exists(current, user_id)
        query = query.where(or_(CategoryModel.user_id.is_(None), CategoryModel.user_id == user_id))
    return db.scalars(query).all()


@app.get("/category/{category_id}", response_model=CategoryOut)
def get_category(category_id: int, current: CurrentUser = any_role, db: Session = Depends(get_db)):
    return get_visible_category(db, current, category_id)


@app.post("/category", response_model=CategoryOut, status_code=201)
def create_personal_category(
    data: CategoryCreate, current: CurrentUser = writers, db: Session = Depends(get_db)
):
    check_own_user_id(current, data.user_id)
    owner_id = data.user_id if data.user_id is not None else current.id
    ensure_user_exists(current, owner_id)
    category = CategoryModel(name=data.name, user_id=owner_id)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@app.post("/category/global", response_model=CategoryOut, status_code=201)
def create_global_category(
    data: GlobalCategoryCreate, current: CurrentUser = admin_only, db: Session = Depends(get_db)
):
    category = CategoryModel(name=data.name, user_id=None)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@app.delete("/category/{category_id}", status_code=204)
def delete_category(category_id: int, current: CurrentUser = writers, db: Session = Depends(get_db)):
    category = get_visible_category(db, current, category_id)
    # глобальні категорії видаляє лише admin, user — тільки свої персональні
    if is_user(current) and category.user_id is None:
        raise ApiError(403, "forbidden", "Access denied: insufficient privileges")
    db.delete(category)
    db.commit()
    return Response(status_code=204)


# Records

@app.post("/record", response_model=RecordOut, status_code=201)
def create_record_endpoint(data: RecordCreate, current: CurrentUser = writers, db: Session = Depends(get_db)):
    return create_record(db, current, data)


@app.get("/record/{record_id}", response_model=RecordOut)
def get_record(record_id: int, current: CurrentUser = any_role, db: Session = Depends(get_db)):
    return get_visible_record(db, current, record_id)


@app.delete("/record/{record_id}", status_code=204)
def delete_record(record_id: int, current: CurrentUser = writers, db: Session = Depends(get_db)):
    record = get_visible_record(db, current, record_id)
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@app.get("/record", response_model=List[RecordOut])
def get_records(
    user_id: Optional[int] = None,
    category_id: Optional[int] = None,
    current: CurrentUser = any_role,
    db: Session = Depends(get_db),
):
    if user_id is None and category_id is None:
        raise ApiError(
            400,
            "invalid_request",
            "At least one query parameter ('user_id' or 'category_id') is required for filtration",
        )
    check_own_user_id(current, user_id)
    if is_user(current):
        # user фільтрує тільки власні записи
        user_id = current.id
    query = select(RecordModel).order_by(RecordModel.id)
    if user_id is not None:
        query = query.where(RecordModel.user_id == user_id)
    if category_id is not None:
        query = query.where(RecordModel.category_id == category_id)
    return db.scalars(query).all()


# JSON-RPC 2.0 (POST /rpc): авторизація по токену, далі та сама логіка, що й у REST

def _json(status_code: int, content, headers=None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=content, headers=headers)


def _rpc_create_record(params: dict, current: CurrentUser, db: Session) -> dict:
    try:
        data = RecordCreate.model_validate(params)
    except ValidationError as error:
        details = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in error.errors())
        raise RpcError(INVALID_PARAMS, details)
    record = create_record(db, current, data)
    return {"record_id": record.id, "status": "created"}


def _rpc_dispatch(method: str, params, current: CurrentUser) -> dict:
    # кожен елемент пакета має власну сесію БД, помилка одного не ламає інші
    if method != "create_record":
        raise RpcError(METHOD_NOT_FOUND, f"Method '{method}' not found")
    if not isinstance(params, dict):
        raise RpcError(INVALID_PARAMS, "Params must be an object")
    with SessionLocal() as db:
        return _rpc_create_record(params, current, db)


def _process_rpc(body: bytes, token: Optional[str]) -> Response:
    # спочатку авторизація (один раз на HTTP-запит), потім розбір JSON
    if token is None:
        return _json(401, error_response(None, UNAUTHORIZED, "Missing access token"),
                     headers={"WWW-Authenticate": "Bearer"})
    try:
        current = resolve_current_user(token)
    except ApiError as error:
        code = API_ERROR_CODES.get(error.status_code, INTERNAL_ERROR)
        return _json(error.status_code, error_response(None, code, error.message), headers=error.headers)

    try:
        payload = json.loads(body)
    except ValueError:
        return _json(200, parse_error_response())

    response = handle_payload(payload, lambda method, params: _rpc_dispatch(method, params, current))
    if response is None:
        # відповіді немає: усі елементи були notification
        return Response(status_code=204)
    return _json(200, response)


@app.post("/rpc")
async def json_rpc(request: Request):
    body = await request.body()
    token = bearer_token(request.headers.get("authorization"))
    # виклики до User Service і БД блокуючі, тому виконуємо їх у пулі потоків
    return await run_in_threadpool(_process_rpc, body, token)
