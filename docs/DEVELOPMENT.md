# Разработка: команды и окружение

Основные команды запускаются из корня репозитория через `make`. Список целей — `Makefile`.

## Первый запуск

1. Docker Desktop запущен.
2. `cp backend/.env.example backend/.env` и заполнить значения (`OPENAI_API_KEY` и др. — вручную).
3. `make up` — Postgres с pgvector.
4. `make migrate` — схема БД (после T1.2).
5. `make backend-dev` — API на http://localhost:8000 (сервер слушает `0.0.0.0`, чтобы телефон достучался
   по LAN-IP; только для доверенных сетей, не запускайте в публичном Wi-Fi), документация на `/docs`.
6. `make mobile-dev` — Expo; QR-код открыть в Expo Go (телефон в той же Wi-Fi).

## Docker и база данных

| Команда | Что делает |
| --- | --- |
| `make up` | Поднимает Postgres и ждёт, пока он станет healthy |
| `make down` | Останавливает контейнеры, данные сохраняются |
| `make db-reset` | Удаляет volume и создаёт чистую БД (данные пропадут) |
| `docker compose -f infra/docker-compose.yml ps` | Статус контейнеров |
| `docker compose -f infra/docker-compose.yml logs -f postgres` | Логи Postgres |
| `docker compose -f infra/docker-compose.yml exec postgres psql -U vocabulary -d vocabulary` | Консоль psql |
| `docker compose -f infra/docker-compose.yml exec postgres psql -U vocabulary -d vocabulary_test` | Тестовая БД |

- Базы: `vocabulary` (разработка) и `vocabulary_test` (тесты). Пользователь и пароль: `vocabulary`.
- Тесты ждут, что `vocabulary_test` существует; если её нет (volume создан до T0.3), выполните `make db-reset`.
- Порт 5432. Если он занят локальным Postgres, остановите его.
- Скрипт из `infra/postgres-init/` выполняется только при первом создании volume; чтобы он
  сработал снова, нужен `make db-reset`.

## Backend

| Команда | Что делает |
| --- | --- |
| `make backend-dev` | FastAPI с автоперезагрузкой на :8000 |
| `make backend-check` | ruff check, ruff format --check, mypy, pytest |
| `make backend-fix` | ruff format и ruff check --fix |
| `make migrate` | `alembic upgrade head` |
| `make migration name=add_book_chunk` | Автогенерация миграции (результат прочитать и поправить) |
| `cd backend && uv add <пакет>` | Добавить зависимость (`--dev` для dev) |
| `cd backend && uv run pytest tests/path -k name` | Выборочный запуск тестов |
| `docker build -t vocab-backend backend` | Сборка production-образа |

Проверка миграции: `alembic upgrade head`, `alembic downgrade -1`, снова `alembic upgrade head`
(из `backend/` через `uv run`).

## Mobile

| Команда | Что делает |
| --- | --- |
| `make mobile-dev` | `expo start` |
| `make mobile-check` | tsc, eslint, steiger, jest |
| `make api-types` | Экспорт OpenAPI из backend и генерация `mobile/src/shared/api/schema.d.ts` |

API на телефоне доступен по LAN-IP компьютера, не по `localhost` (`EXPO_PUBLIC_API_URL` в `mobile/.env`).

## Evals (платные вызовы OpenAI)

`cd backend && uv run python -m evals run <suite>`

## Фоновые задачи

- По умолчанию воркер Procrastinate работает внутри API (`JOBS_RUN_IN_PROCESS=true`,
  `JOBS_WORKER_CONCURRENCY=2` в `backend/.env`).
- Отдельный процесс воркера пока не поддерживается: задачам нужен runtime с сессией БД и
  AI-провайдером, который собирается только в lifespan API (ADR-016).
- Схема Procrastinate ставится миграцией 0002; версия библиотеки закреплена точно, при её
  обновлении добавляется новая ревизия Alembic.

## Mobile

- Expo SDK 58, Expo Router: маршруты лежат в `mobile/app/`, FSD-слои — в `mobile/src/`
  (`app/` внутри `src` — это слой FSD, а не маршруты; корень маршрутов задан в `app.json`).
- Первый запуск: `cd mobile && npm install`, затем `mobile/.env` по образцу `.env.example`
  (`EXPO_PUBLIC_API_URL` — LAN-IP компьютера), `make mobile-dev` из корня репозитория (или `npm start` в
  `mobile/`), QR-код — в Expo Go. Expo Go для SDK 58 требует входа в один и тот же бесплатный
  аккаунт Expo и в приложении, и в CLI (`npx expo login`).
- Скрипты: `npm run typecheck | lint | lint:fsd | test | format`; всё сразу — `make mobile-check`.
- Зависимости с нативной частью — только через `npx expo install` и только из Expo Go (ADR-002).

## AI

- В `backend/.env`: `OPENAI_API_KEY` и `OPENAI_MODEL` (например, `gpt-4o-mini`).
- Ручная проверка всех AI-функций на реальном API: `cd backend && uv run python -m scripts.ai_smoke`.
  Скрипт делает около 7 платных запросов (порядка нескольких центов) и в CI не запускается.

