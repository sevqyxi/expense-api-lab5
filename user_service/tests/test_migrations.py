"""Перевірка міграції 0002 на старих користувачах з ЛР3 (без логіна й пароля)."""
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from database import BASE_DIR, engine


def alembic_config():
    config = Config(os.path.join(BASE_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BASE_DIR, "alembic"))
    return config


def test_migration_keeps_legacy_users(client):
    config = alembic_config()
    # повертаємо схему ЛР3 і додаємо "старого" користувача
    command.downgrade(config, "0001")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (name) VALUES ('Old user from lab 3')"))

    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT username, password_hash, role FROM users WHERE name = 'Old user from lab 3'")
        ).one()
    assert row.username is None
    assert row.password_hash is None
    assert row.role == "user"

    # старий користувач без пароля не може увійти
    response = client.post("/login", json={"username": "Old user from lab 3", "password": "anything1"})
    assert response.status_code == 401
