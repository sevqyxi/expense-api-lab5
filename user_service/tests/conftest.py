import os
import sys

from dotenv import load_dotenv

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(SERVICE_DIR)
# proto/ лежить у корені проєкту, тому він потрібен у шляху імпорту
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, SERVICE_DIR)
load_dotenv(os.path.join(ROOT_DIR, ".env"))

# тести працюють з окремою БД users_test, основна БД не змінюється
TEST_DB_NAME = os.getenv("TEST_USER_DB", "users_test")
assert "test" in TEST_DB_NAME, "Тестова БД повинна містити 'test' у назві"

_user = os.getenv("POSTGRES_USER", "postgres")
_password = os.getenv("POSTGRES_PASSWORD", "postgres")
_port = os.getenv("USER_DB_PORT", "5433")
_server_url = f"postgresql+psycopg://{_user}:{_password}@localhost:{_port}"

os.environ["USER_DATABASE_URL"] = f"{_server_url}/{TEST_DB_NAME}"
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-0123456789")
# gRPC-сервер у тестах піднімається на окремому порту
os.environ["USER_SERVICE_GRPC_PORT"] = os.getenv("TEST_USER_GRPC_PORT", "50061")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from database import SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402
from models import UserModel  # noqa: E402
from security import hash_password  # noqa: E402

PASSWORD = "Secret12345"


def create_test_database():
    # створюємо тестову БД, якщо її ще немає
    admin_engine = create_engine(f"{_server_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()


def clear_tables():
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def app_client():
    create_test_database()
    # with запускає lifespan застосунку: міграції Alembic і gRPC-сервер
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(app_client):
    # кожен тест починається з порожньої таблиці користувачів
    clear_tables()
    yield app_client
    clear_tables()


def make_user(client, username, role="user"):
    # користувач створюється в БД з потрібною роллю, а токен отримується через POST /login
    with SessionLocal() as db:
        user = UserModel(username=username, name=username, password_hash=hash_password(PASSWORD), role=role)
        db.add(user)
        db.commit()
        user_id = user.id
    response = client.post("/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"id": user_id, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def user(client):
    return make_user(client, "alice")


@pytest.fixture
def other_user(client):
    return make_user(client, "bob")


@pytest.fixture
def auditor(client):
    return make_user(client, "auditor", role="auditor")


@pytest.fixture
def admin(client):
    return make_user(client, "admin", role="admin")
