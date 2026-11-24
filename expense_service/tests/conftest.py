import os
import sys
from concurrent import futures

from dotenv import load_dotenv

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(SERVICE_DIR)
# proto/ лежить у корені проєкту, тому він потрібен у шляху імпорту
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, SERVICE_DIR)
load_dotenv(os.path.join(ROOT_DIR, ".env"))

# тести працюють з окремою БД expenses_test, основна БД не змінюється
TEST_DB_NAME = os.getenv("TEST_EXPENSE_DB", "expenses_test")
assert "test" in TEST_DB_NAME, "Тестова БД повинна містити 'test' у назві"

_user = os.getenv("POSTGRES_USER", "postgres")
_password = os.getenv("POSTGRES_PASSWORD", "postgres")
_port = os.getenv("EXPENSE_DB_PORT", "5434")
_server_url = f"postgresql+psycopg://{_user}:{_password}@localhost:{_port}"

os.environ["EXPENSE_DATABASE_URL"] = f"{_server_url}/{TEST_DB_NAME}"
# Expense Service у тестах працює з фейковим AuthService на окремому порту
AUTH_TEST_PORT = int(os.getenv("TEST_AUTH_GRPC_PORT", "50071"))
os.environ["USER_SERVICE_GRPC_ADDR"] = f"localhost:{AUTH_TEST_PORT}"

import grpc  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from database import engine  # noqa: E402
from main import app  # noqa: E402
from proto import auth_pb2, auth_pb2_grpc  # noqa: E402


class FakeAuthService(auth_pb2_grpc.AuthServiceServicer):
    # поводиться як User Service: невалідний токен -> UNAUTHENTICATED
    def __init__(self):
        self.roles = {}
        self.tokens = {}

    def reset(self):
        self.roles.clear()
        self.tokens.clear()

    def add_user(self, user_id: int, role: str) -> str:
        token = f"token-{user_id}-{role}"
        self.roles[user_id] = role
        self.tokens[token] = user_id
        return token

    def ValidateToken(self, request, context):
        user_id = self.tokens.get(request.token)
        if user_id is None:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid access token")
        return auth_pb2.ValidateTokenResponse(is_valid=True, user_id=str(user_id), roles=[self.roles[user_id]])

    def UserExists(self, request, context):
        return auth_pb2.UserExistsResponse(exists=request.user_id in self.roles)


def create_test_database():
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
        connection.execute(text("TRUNCATE records, categories RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def auth_service():
    servicer = FakeAuthService()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    auth_pb2_grpc.add_AuthServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"localhost:{AUTH_TEST_PORT}")
    server.start()
    yield servicer
    server.stop(grace=0)


@pytest.fixture(scope="session")
def app_client(auth_service):
    create_test_database()
    # with запускає lifespan застосунку, тобто міграції Alembic
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(app_client, auth_service):
    # кожен тест починається з порожніх таблиць і без користувачів у фейковому AuthService
    clear_tables()
    auth_service.reset()
    yield app_client
    clear_tables()


def make_user(auth_service, user_id, role="user"):
    token = auth_service.add_user(user_id, role)
    return {"id": user_id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def user(client, auth_service):
    return make_user(auth_service, 1, "user")


@pytest.fixture
def other_user(client, auth_service):
    return make_user(auth_service, 2, "user")


@pytest.fixture
def auditor(client, auth_service):
    return make_user(auth_service, 3, "auditor")


@pytest.fixture
def admin(client, auth_service):
    return make_user(auth_service, 4, "admin")
