# Лабораторна робота №5

**Дисципліна:** Технології розроблення серверних компонентів

**Тема:** Мікросервісна декомпозиція

## Опис

Монолітний застосунок з ЛР4 розділено на два мікросервіси, кожен зі своєю базою PostgreSQL.

- **User Service** — користувачі, реєстрація, вхід, JWT, ролі `user`, `auditor`, `admin`. REST на порту `8000`, gRPC на порту `50051`. База `users`.
- **Expense Service** — категорії, записи витрат, JSON-RPC 2.0 на `POST /rpc`. REST на порту `8001`. База `expenses`.

Expense Service не перевіряє JWT сам. Токен і роль він отримує від User Service синхронним gRPC-викликом. Токен передається в gRPC metadata (`authorization: Bearer <token>`). Якщо User Service недоступний, Expense Service повертає `503`.

Використані технології: Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL 16, PyJWT, Argon2id (cryptography), gRPC (grpcio), JSON-RPC 2.0, Docker Compose, Pytest, GitHub Actions, Bruno.

Логіка варіанта 2 з ЛР3 збережена: `V = (4606 % 3) + 1 = 2`, персональні та глобальні категорії.

## Структура

```
proto/auth.proto          контракт gRPC
user_service/             User Service (REST, gRPC-сервер, перехоплювач, міграції, тести)
expense_service/          Expense Service (REST, POST /rpc, gRPC-клієнт, міграції, тести)
bruno_collection/         колекція Bruno (YAML)
docker-compose.yaml       дві бази PostgreSQL і два сервіси
```

## Налаштування

Створіть файл `.env` з прикладу і задайте `JWT_SECRET_KEY`:

```bash
cp .env.example .env
```

Якщо порти `5433` або `5434` зайняті, змініть `USER_DB_PORT` і `EXPENSE_DB_PORT` у `.env`. Якщо залишилися контейнери ЛР4, зупиніть їх: `docker compose -f ../expense-api-lab4/docker-compose.yaml down`.

## Запуск через Docker Compose

```bash
docker compose up -d --build
docker compose ps
```

Перевірка:

```bash
curl -s http://127.0.0.1:8000/healthz/ready
curl -s http://127.0.0.1:8001/healthz/ready
```

Створити admin (потрібно для Bruno і перевірок):

```bash
docker compose exec user-service python create_user.py admin Admin12345 --role admin
```

Зупинка: `docker compose down`. Щоб видалити дані баз: `docker compose down -v`.

## Запуск без Docker

Потрібні Python 3.12 і запущені бази. Бази піднімаються через Docker Compose:

```bash
docker compose up -d user-db expense-db
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. proto/auth.proto
```

Команда `protoc` створює файли `proto/auth_pb2.py` і `proto/auth_pb2_grpc.py`. Її треба виконати один раз і після кожної зміни `auth.proto`.

У двох окремих терміналах:

```bash
# термінал 1: User Service (REST 8000 + gRPC 50051)
cd user_service && PYTHONPATH=.. uvicorn main:app --port 8000

# термінал 2: Expense Service (REST 8001)
cd expense_service && PYTHONPATH=.. uvicorn main:app --port 8001
```

Admin для локального запуску: `cd user_service && PYTHONPATH=.. python create_user.py admin Admin12345 --role admin`.

## Тести

Тести створюють тестові бази `users_test` і `expenses_test` автоматично. Потрібні запущені `user-db` і `expense-db`, а також згенеровані stubs.

```bash
cd user_service && pytest
cd expense_service && pytest
```

Тести Expense Service працюють з фейковим AuthService, тому User Service для них запускати не потрібно.

## Перевірка через термінал

Реєстрація, вхід і збереження токена:

```bash
curl -s -X POST http://127.0.0.1:8000/register -H 'Content-Type: application/json' \
  -d '{"username":"ivan_01","password":"Secret12345"}'

TOKEN=$(curl -s -X POST http://127.0.0.1:8000/login -H 'Content-Type: application/json' \
  -d '{"username":"ivan_01","password":"Secret12345"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Глобальна категорія (потрібен admin-токен, у прикладі він у `$ADMIN`) і запис через REST:

```bash
curl -s -X POST http://127.0.0.1:8001/category/global -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d '{"name":"Food"}'

curl -s -X POST http://127.0.0.1:8001/record -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"category_id":1,"amount":250.50}'
```

JSON-RPC: одиночний запит і пакетний запит:

```bash
curl -s -X POST http://127.0.0.1:8001/rpc -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"create_record","params":{"category_id":1,"amount":100},"id":1}'

curl -s -X POST http://127.0.0.1:8001/rpc -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '[{"jsonrpc":"2.0","method":"create_record","params":{"category_id":1,"amount":100},"id":1},
       {"jsonrpc":"2.0","method":"create_record","params":{"category_id":1,"amount":45.5},"id":2}]'
```

Запит без токена дає `401`, а запит із неправильною роллю дає помилку `-32003` у JSON-тілі.

gRPC напряму (встановлення: `brew install grpcurl`):

```bash
grpcurl -plaintext -import-path proto -proto auth.proto \
  -H "authorization: Bearer $TOKEN" -d "{\"token\": \"$TOKEN\"}" \
  localhost:50051 auth.AuthService/ValidateToken

# без metadata сервер відхиляє виклик (код Unauthenticated)
grpcurl -plaintext -import-path proto -proto auth.proto \
  -d "{\"token\": \"$TOKEN\"}" localhost:50051 auth.AuthService/ValidateToken
```

Недоступність User Service: `docker compose stop user-service`, після чого `GET http://127.0.0.1:8001/category` з токеном дає `503`. Потім `docker compose start user-service`.

## Перевірка через Bruno

1. Відкрити папку `bruno_collection` через Open Collection.
2. Вибрати середовище `Local`. У ньому два адреси: `userBaseUrl` (8000) і `expenseBaseUrl` (8001).
3. Запустити всю колекцію через Runner. Папка `06 JSON-RPC` перевіряє пакети, помилки і статуси, папка `07 gRPC checks` перевіряє взаємодію з User Service через Expense Service.

Колекція очищає створені дані в кінці. Її можна запускати повторно.

## GitHub Actions

Файл `.github/workflows/ci.yml`. CI піднімає дві бази PostgreSQL, генерує stubs і запускає тести обох сервісів.
