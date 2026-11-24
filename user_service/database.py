import os

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Змінні оточення читаються з файлу .env (якщо він є).
# Вже задані змінні оточення мають пріоритет над .env
load_dotenv()

DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_PORT = os.getenv("USER_DB_PORT", "5433")

# власна БД User Service, Expense Service до неї не звертається
DATABASE_URL = os.getenv(
    "USER_DATABASE_URL",
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@localhost:{DB_PORT}/users",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Base(DeclarativeBase):
    pass


def get_db():
    # окрема сесія БД на кожен запит
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations():
    # застосовуємо всі міграції Alembic до останньої версії
    config = Config(os.path.join(BASE_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BASE_DIR, "alembic"))
    command.upgrade(config, "head")


def database_is_available() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
