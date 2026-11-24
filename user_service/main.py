import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import database_is_available, get_db, run_migrations
from errors import ApiError
from grpc_server import start_grpc_server
from models import ROLE_ADMIN, ROLE_AUDITOR, ROLE_USER, UserModel
from schemas import LoginIn, RegisterIn, RoleUpdate, TokenOut, UserOut
from security import (
    create_access_token,
    get_current_user,
    get_jwt_secret,
    get_token_lifetime,
    hash_password,
    require_roles,
    verify_password,
)

GRPC_PORT = int(os.getenv("USER_SERVICE_GRPC_PORT", "50051"))
# максимальне значення для колонки INTEGER у PostgreSQL
MAX_ID = 2_147_483_647


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_jwt_secret()  # без JWT_SECRET_KEY застосунок не запуститься
    run_migrations()
    # gRPC-сервер для Expense Service працює в тому самому процесі
    grpc_server = start_grpc_server(GRPC_PORT)
    yield
    grpc_server.stop(grace=2)


app = FastAPI(title="User Service", lifespan=lifespan)

# залежності для перевірки ролей
any_role = Depends(get_current_user)
readers = Depends(require_roles(ROLE_AUDITOR, ROLE_ADMIN))
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


def not_found(name: str, obj_id) -> ApiError:
    return ApiError(404, "not_found", f"{name} with id {obj_id} not found")


def get_or_404(db: Session, model, obj_id: int, name: str):
    obj = db.get(model, obj_id) if 0 < obj_id <= MAX_ID else None
    if obj is None:
        raise not_found(name, obj_id)
    return obj


def check_own_user_id(current: UserModel, user_id: int):
    # звичайний user не може відкрити чужий профіль: для нього чужих даних "не існує"
    if current.role == ROLE_USER and user_id != current.id:
        raise not_found("User", user_id)


# Системні маршрути (публічні)

@app.get("/healthz/live")
def healthz_live():
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/healthz/ready")
def healthz_ready():
    if not database_is_available():
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})
    return {"status": "ready", "database": "ok"}


# Реєстрація та вхід (публічні)

@app.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(UserModel).where(UserModel.username == data.username)):
        raise ApiError(409, "conflict", f"Username '{data.username}' is already taken")
    # нова реєстрація завжди отримує роль user
    user = UserModel(
        username=data.username,
        name=data.name or data.username,
        password_hash=hash_password(data.password),
        role=ROLE_USER,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "conflict", f"Username '{data.username}' is already taken")
    db.refresh(user)
    return user


@app.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(UserModel).where(UserModel.username == data.username))
    if user is None or not verify_password(data.password, user.password_hash):
        raise ApiError(401, "unauthorized", "Invalid username or password")
    return TokenOut(
        access_token=create_access_token(user),
        expires_in=int(get_token_lifetime().total_seconds()),
    )


# Users

@app.get("/users", response_model=List[UserOut])
def get_users(current: UserModel = readers, db: Session = Depends(get_db)):
    return db.scalars(select(UserModel).order_by(UserModel.id)).all()


@app.get("/user/{user_id}", response_model=UserOut)
def get_user(user_id: int, current: UserModel = any_role, db: Session = Depends(get_db)):
    check_own_user_id(current, user_id)
    return get_or_404(db, UserModel, user_id, "User")


@app.delete("/user/{user_id}", status_code=204)
def delete_user(user_id: int, current: UserModel = admin_only, db: Session = Depends(get_db)):
    user = get_or_404(db, UserModel, user_id, "User")
    # записи та персональні категорії лежать в іншій БД (Expense Service),
    # тому тут вони не видаляються: зв'язку між базами немає
    db.delete(user)
    db.commit()
    return Response(status_code=204)


@app.patch("/user/{user_id}/role", response_model=UserOut)
def change_user_role(
    user_id: int, data: RoleUpdate, current: UserModel = admin_only, db: Session = Depends(get_db)
):
    user = get_or_404(db, UserModel, user_id, "User")
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user
