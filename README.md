# Лабораторна робота №5

**Дисципліна:** Технології розроблення серверних компонентів

**Тема:** Мікросервісна декомпозиція

## Опис

У цій лабораторній роботі застосунок з ЛР4 розділено на два мікросервіси:

- User Service — реєстрація, автентифікація, JWT та ролі користувачів.
- Expense Service — робота з категоріями та записами витрат.

Кожен сервіс має власну базу даних PostgreSQL. Взаємодія між сервісами реалізована через gRPC. Для перевірки токенів та ролей використовується gRPC Interceptor.

В Expense Service додано ендпоінт `POST /rpc` з підтримкою одиночних та пакетних JSON-RPC 2.0 запитів.

Логіку варіанта 2 з ЛР3, персональні та глобальні категорії, а також обмеження доступу з ЛР4 збережено.

## Використані технології

Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL, JWT, gRPC, Protobuf, JSON-RPC 2.0, Docker Compose, Pytest, Bruno.

## Структура проєкту

```
user_service/       — сервіс користувачів
expense_service/    — сервіс витрат
proto/              — контракт gRPC
bruno_collection/   — колекція запитів Bruno
docker-compose.yaml — конфігурація Docker
```

## Запуск проєкту

Створити файл `.env`:

```bash
cp .env.example .env
```

Задати власний `JWT_SECRET_KEY` довжиною не менше 32 символів у файлі `.env`.

Запустити контейнери:

```bash
docker compose up -d --build
docker compose ps
```

Порти сервісів:

- User Service — 8000
- Expense Service — 8001
- gRPC — 50051

Перевірка доступності сервісів:

```bash
curl http://localhost:8000/healthz/ready
curl http://localhost:8001/healthz/ready
```

Створення тестового адміністратора:

```bash
docker compose exec user-service python create_user.py admin Admin12345 --role admin
```

Зупинка контейнерів:

```bash
docker compose down
```

## gRPC

Контракт описано у файлі `proto/auth.proto`.

Реалізовані методи:

- `ValidateToken` — перевірка токена та отримання інформації про користувача.
- `UserExists` — перевірка існування користувача.

Токен передається через metadata. Доступ до методу `UserExists` обмежено ролями.

При недоступності User Service сервіс витрат повертає статус 503.

## JSON-RPC

Ендпоінт: `POST /rpc`.

Приклад одиночного запиту:

```json
{
  "jsonrpc": "2.0",
  "method": "create_record",
  "params": {
    "category_id": 1,
    "amount": 100
  },
  "id": 1
}
```

Приклад пакетного запиту:

```json
[
  {
    "jsonrpc": "2.0",
    "method": "create_record",
    "params": {"category_id": 1, "amount": 100},
    "id": 1
  },
  {
    "jsonrpc": "2.0",
    "method": "create_record",
    "params": {"category_id": 1, "amount": 45.5},
    "id": 2
  }
]
```

Для виконання запитів необхідний JWT-токен та наявна категорія.

## Тестування через Bruno

1. Відкрити папку `bruno_collection`.
2. Вибрати середовище `Local`.
3. Запустити колекцію через Runner.

Колекція містить перевірки REST API, авторизації, ролей, JSON-RPC та gRPC.

Результат тестування початкової колекції:

- Passed — 75
- Failed — 0
- Skipped — 0

Додатково створено та перевірено чотири нативні gRPC-запити:

- Перевірка дійсного токена.
- Запит без metadata авторизації.
- Виклик UserExists звичайним користувачем.
- Виклик UserExists адміністратором.

Для ручного запуску gRPC-запитів потрібно отримати актуальні токени до виконання папки Cleanup. Використовується файл `proto/auth.proto`.

## Автоматичні тести

Для запуску тестів необхідні встановлені залежності, запущені бази даних та згенеровані Protobuf stubs.

```bash
(cd user_service && python -m pytest)
(cd expense_service && python -m pytest)
```

Також у проєкті налаштовано GitHub Actions для автоматичного тестування.