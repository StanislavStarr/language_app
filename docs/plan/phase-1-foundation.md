# Фаза 1 — Фундамент (~22 ч)

**Результат:** на телефоне через Expo Go открывается приложение, проходит анонимный вход и
onboarding, пользователь сохранён в БД, CI зелёный.

---

## Backend

### T1.1 — Каркас FastAPI                                        ~3 ч   [x]

**Цель:** запускаемое приложение с конфигурацией, логами, единым форматом ошибок и `/health`.
**Контекст:** ARCHITECTURE.md §3, §4, §7 (соглашения об ошибках); `backend/CLAUDE.md`.
**Сделать:**
- `uv init` в `backend/`, Python 3.13; зависимости: `fastapi[standard]`, `pydantic-settings`,
  `structlog`, `httpx`; dev: `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `respx`;
- `pyproject.toml`: настройки ruff (PEP 8, line-length 100, правила `E,F,W,I,N,UP,B,A,C4,SIM,RET,ARG,PTH,PL,RUF,ASYNC,S`),
  mypy strict, pytest (asyncio_mode=auto);
- `app/main.py` с `create_app()`; `app/api.py` с роутером `/api/v1`;
- `core/config.py` (`Settings`, чтение `backend/.env`), `core/logging.py` (structlog JSON,
  middleware с `X-Request-ID`), `core/errors.py` (`AppError(code, message, status, details)`
  + обработчики: AppError, RequestValidationError → `validation_error`, необработанное → `internal_error`);
- `GET /health` → `{"status": "ok"}`;
- `backend/Dockerfile` (multi-stage, uv, non-root пользователь).

**Приёмка:** `make backend-dev` поднимает сервер; `/docs` открывается; ответ ошибки валидации в
формате `{"error": {"code": "validation_error", ...}}`; `make backend-check` зелёный.
**Тесты:** health; формат AppError; формат ошибки валидации; request id в ответе.
**Skills:** `backend-module`, `backend-testing`.

> Итог: каркас FastAPI, конфиг, structlog с `X-Request-ID`, единый формат ошибок, `/health`, Dockerfile и 8 тестов. Отличия: `AppError` задаёт `code`/`status_code` атрибутами подкласса (зафиксировано в ARCHITECTURE §7); `/health` лежит вне `/api/v1`, в `app/core/health.py`. Не сделано: HEALTHCHECK и пин тега образа в Dockerfile, приём входящего `X-Request-ID`.

### T1.2 — База данных и Alembic                                 ~3 ч   [x]

**Цель:** async-подключение к Postgres, миграции, справочник языков.
**Контекст:** ARCHITECTURE.md §5, §12; skill `backend-migration`.
**Сделать:**
- `core/database.py`: async engine (`postgresql+psycopg`), `async_sessionmaker`, `Base` с naming convention
  для ограничений; зависимость `get_session`;
- `GET /ready` — проверка `SELECT 1`;
- Alembic с async `env.py`, автозагрузка моделей всех модулей;
- миграция 0001: `CREATE EXTENSION vector`, `pg_trgm`; таблица `language` + данные (`en`, `ru`);
- модуль `languages`: модель, репозиторий, `GET /languages`;
- `tests/conftest.py`: тестовая БД `vocabulary_test`, миграции один раз на сессию, транзакция
  с откатом на каждый тест, `AsyncClient` с переопределённой сессией.

**Приёмка:** `make migrate` применяет миграции; `alembic downgrade base` и снова `upgrade head`
работают; `/ready` = 200 при живой БД и 503 без неё.
**Тесты:** `/ready`; `GET /languages`; миграции туда-обратно.

> Итог: `core/database.py`, async Alembic, миграция 0001 (расширения, `language`, `en`/`ru`), модуль `languages`, `/ready`, транзакционные тесты на `vocabulary_test`. Отличия: `/ready` в `core/health.py` с кодом `database_unavailable` (503, внесён в ARCHITECTURE §7); `database_url` имеет локальное значение по умолчанию; `alembic/` добавлен в mypy.

### T1.3 — Фоновые задачи на Procrastinate                       ~3 ч   [ ]

**Цель:** очередь задач в Postgres и воркер внутри процесса API.
**Контекст:** ARCHITECTURE.md §10; DECISIONS ADR-005; документация Procrastinate (применение
схемы/миграций, `run_worker_async`, `RetryStrategy`, тестирование через `InMemoryConnector`).
**Сделать:**
- `core/jobs.py`: `procrastinate.App` с `PsycopgConnector`, регистрация задач модулей;
- миграция Alembic, которая применяет схему Procrastinate (по официальной инструкции для версии);
- запуск/остановка воркера в lifespan при `JOBS_RUN_IN_PROCESS=true` (конкурентность из настроек);
- восстановление «зависших» задач (`doing` старше 15 минут) при старте;
- служебная задача `ping_job` для проверки;
- фикстура для тестов задач (in-memory connector).

**Приёмка:** отложенная `ping_job` выполняется воркером в процессе API (видно в логах);
остановка сервера корректно гасит воркер.
**Тесты:** задача ставится в очередь и выполняется в тестовом режиме.

### T1.4 — Вход по устройству и профиль                          ~4 ч   [ ]

**Цель:** анонимный аккаунт, JWT, профиль с onboarding.
**Контекст:** ARCHITECTURE.md §5.1, §8; DECISIONS ADR-003.
**Сделать:**
- модели `user`, `auth_identity` + миграция;
- `core/security.py`: выпуск и проверка JWT (HS256, TTL из настроек), хэш секрета, сравнение в постоянное время;
- `POST /auth/device` (`install_id` uuid, `device_secret` 43–128 символов);
- зависимость `get_current_user` (401 с кодами `token_missing`, `token_invalid`, `token_expired`);
- `GET /users/me`, `PATCH /users/me` (`cefr_level`, `answer_language`, `complete_onboarding: bool`);
  языки RU/EN проставляются при создании пользователя.

**Приёмка:** новое устройство → новый пользователь; повтор с тем же секретом → тот же пользователь;
неверный секрет → 401 `invalid_device_credentials`.
**Тесты:** все ветки входа; истёкший токен; PATCH с неверным CEFR → 422.

### T1.5 — Лимиты использования                                  ~2 ч   [ ]

**Цель:** общий механизм суточных лимитов и частоты запросов.
**Контекст:** ARCHITECTURE.md §11.
**Сделать:**
- модуль `usage`: таблица `daily_usage`, сервис `consume(user_id, kind, amount=1)` с атомарным
  `INSERT … ON CONFLICT DO UPDATE … RETURNING count`, исключение `UsageLimitExceeded`
  (код `usage_limit_exceeded`, `details: {kind, limit, resets_at}`);
- лимиты в `Settings`;
- `core/rate_limit.py`: скользящее окно in-memory на пользователя, зависимость для роутеров,
  код `rate_limited` + заголовок `Retry-After`.

**Тесты:** конкурентные `consume` не превышают лимит; сброс по дням (часовой пояс UTC);
rate limit отдаёт 429.

### T1.6 — CI для backend                                        ~1 ч   [ ]

**Сделать:** `.github/workflows/backend.yml`: триггер на изменения `backend/**`; uv с кэшем;
service container `pgvector/pgvector:pg17`; `ruff check`, `ruff format --check`, `mypy`, `pytest`.
**Приёмка:** PR с ошибкой форматирования падает; чистый PR проходит.

## Mobile

### T1.7 — Каркас Expo-приложения по FSD                          ~3 ч   [ ]

**Цель:** приложение запускается в Expo Go, структура FSD, линтеры и тесты настроены.
**Контекст:** `mobile/CLAUDE.md`; ARCHITECTURE.md §3 (Mobile); DECISIONS ADR-002, ADR-012.
**Сделать:**
- `npx create-expo-app@latest mobile` (TypeScript, Expo Router); убрать демо-экраны;
- структура `mobile/app/` (маршруты) и `mobile/src/{app,pages,widgets,features,entities,shared}`;
  алиас `@/` → `src/`;
- ESLint flat config (TypeScript strict rules, react-hooks, import order), Prettier, `steiger`;
- `jest-expo` + `@testing-library/react-native`;
- `shared/ui/theme`: цвета (светлая/тёмная), отступы, радиусы, типографика;
  базовые компоненты: `Screen`, `AppText`, `Button`, `TextField`, `LoadingState`, `ErrorState`, `EmptyState`;
- `shared/config/env.ts`: `EXPO_PUBLIC_API_URL` с проверкой при старте;
- скрипты `npm run typecheck|lint|lint:fsd|test`.

**Приёмка:** `npx expo start` → приложение открывается на телефоне; `make mobile-check` зелёный.
**Тесты:** рендер `Button` и `ErrorState`.
**Skills:** `mobile-fsd-slice`, `mobile-testing`.

### T1.8 — API-слой и пробуждение сервера                         ~3 ч   [ ]

**Цель:** типизированный клиент API, нормализованные ошибки, обработка холодного старта.
**Контекст:** ARCHITECTURE.md §7, §12; DECISIONS ADR-010; skill `mobile-api-sync`.
**Сделать:**
- `backend/scripts/export_openapi.py` → `backend/openapi.json`; `npm run api:generate` →
  `src/shared/api/schema.d.ts` (`openapi-typescript`);
- `src/shared/api/client.ts` на `openapi-fetch`: базовый URL, middleware авторизации (токен из
  session store), при 401 — один повтор после повторного входа;
- `ApiError` (`code`, `message`, `status`, `details`) и `toApiError()` для всех ответов и сетевых ошибок;
- TanStack Query `QueryClient`: ретраи только для сетевых ошибок и 502/503/504 (экспоненциально,
  до ~90 с суммарно — Render просыпается около минуты), без ретраев на 4xx;
- глобальный баннер «Сервер просыпается…», пока идут такие ретраи.

**Тесты:** `toApiError` для формата ошибки backend, сетевой ошибки, неизвестного ответа;
политика ретраев.

### T1.9 — Вход по устройству на клиенте                          ~2 ч   [ ]

**Сделать:**
- `entities/session`: хранение `install_id`/`device_secret` в `expo-secure-store`,
  генерация через `expo-crypto`; Zustand-store с токеном (токен держим в памяти, креды — в secure store);
- `features/device-sign-in`: вход при старте, повторный вход при 401;
- `src/app/providers` (QueryClient, тема, GestureHandlerRootView, BottomSheetModalProvider);
  `app/_layout.tsx` держит сплэш до готовности сессии; экран ошибки входа с повтором.

**Приёмка:** первый запуск создаёт пользователя; перезапуск — тот же пользователь.
**Тесты:** генерация и чтение кредов (mock secure-store); повтор при 401.

### T1.10 — Onboarding, вкладки, профиль                          ~3 ч   [ ]

**Сделать:**
- `pages/onboarding`: уровень CEFR (A1–C2 с подписями), язык ответов «Спроси книгу»,
  предупреждение о привязке к устройству, уведомление о том, что тексты книг обрабатываются
  через OpenAI; кнопка «Начать» → `PATCH /users/me`;
- guard в `app/_layout.tsx`: onboarding не пройден → `/onboarding`;
- вкладки `(tabs)`: Библиотека, Словарь, Профиль (заглушки у первых двух);
- `pages/profile`: изменение уровня и языка ответов.

**Приёмка:** новый пользователь видит onboarding, после него — вкладки; изменения в профиле
сохраняются на сервере.
**Тесты:** форма onboarding отправляет корректные данные.

### T1.11 — CI для mobile                                         ~1 ч   [ ]

**Сделать:** `.github/workflows/mobile.yml`: изменения `mobile/**`; Node LTS с кэшем;
`npm ci`, `typecheck`, `lint`, `lint:fsd`, `test`; проверка, что `schema.d.ts` совпадает с
`backend/openapi.json` (генерация + `git diff --exit-code`).
