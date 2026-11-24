"""Створення користувача з будь-якою роллю (для admin і auditor).

Приклад:
    python create_user.py admin Admin12345 --role admin
Якщо користувач з таким логіном уже існує, йому оновлюються пароль і роль.
"""
import argparse

from sqlalchemy import select

from database import SessionLocal, run_migrations
from models import ROLES, UserModel
from schemas import RegisterIn
from security import hash_password


def main():
    parser = argparse.ArgumentParser(description="Create or update a user with a given role")
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("--role", choices=ROLES, default="user")
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    # ті самі правила валідації, що й у POST /register
    data = RegisterIn(username=args.username, password=args.password, name=args.name)

    run_migrations()
    with SessionLocal() as db:
        user = db.scalar(select(UserModel).where(UserModel.username == data.username))
        if user is None:
            user = UserModel(username=data.username, name=data.name or data.username)
            db.add(user)
        user.password_hash = hash_password(data.password)
        user.role = args.role
        db.commit()
        print(f"User '{user.username}' (id={user.id}) saved with role '{user.role}'")


if __name__ == "__main__":
    main()
