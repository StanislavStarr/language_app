# Неделя 1 — Foundation (шаги 7–24)

## Цель недели

К концу недели работает сквозной путь: пользователь нажимает `/start` в Telegram, открывает Mini App,
проходит аутентификацию, выбирает язык и уровень — и эти данные лежат в PostgreSQL. Всё запускается
одной командой `docker compose up`, CI на GitHub зелёный.

Ориентировочное время: 25 часов.

Перед началом прочитайте [01-primer-python-backend.md](01-primer-python-backend.md) — разделы 1–5.

---

## Шаг 7. Скелет FastAPI: настройки, приложение, `/health`

### Цель

Backend запускается локально, отвечает на `/health`, показывает документацию на `/docs`.

### Файлы

```text
backend/
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── main.py
│   └── common/
│       ├── __init__.py
│       └── settings.py
└── tests/
    └── __init__.py
```

### Действия

Создайте `backend/pyproject.toml`:

```toml
[project]
name = "vocabulary-backend"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.141.0",
    "uvicorn[standard]>=0.34.0",
    "pydantic>=2.11.0",
    "pydantic-settings>=2.8.0",
    "sqlalchemy>=2.0.49",
    "asyncpg>=0.30.0",
    "alembic>=1.15.0",
    "celery[redis]>=5.6.0",
    "redis>=5.2.0",
    "httpx>=0.28.0",
    "pyjwt>=2.10.0",
    "openai>=1.70.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.25.0",
    "ruff>=0.9.0",
    "mypy>=1.15.0",
]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "ASYNC", "RUF"]

[tool.mypy]
python_version = "3.13"
strict = true
plugins = ["pydantic.mypy"]
warn_unused_ignores = true
disallow_any_explicit = true

[[tool.mypy.overrides]]
module = ["celery.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

Установите зависимости:

```bash
cd backend
uv sync
```

Появятся `.venv/` и `uv.lock`. Lock-файл **коммитится** — он гарантирует одинаковые версии локально,
в Docker и на CI.

Создайте `backend/app/common/settings.py`:

```python
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore", case_sensitive=False)

    app_env: Literal["local", "staging", "production"] = "local"
    app_debug: bool = False
    api_base_path: str = "/api/v1"
    secret_key: str
    access_token_ttl_days: int = 30

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "vocabulary"
    postgres_user: str = "vocabulary"
    postgres_password: str

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    telegram_bot_token: str = ""
    telegram_auth_max_age_seconds: int = 86_400
    admin_telegram_ids: str = ""
    mini_app_url: str = ""

    yandex_dictionary_api_key: str = ""
    yandex_dictionary_timeout_seconds: float = 5.0
    wiktionary_timeout_seconds: float = 5.0
    wikimedia_user_agent: str = "english-vocabulary-app/0.1"

    openai_api_key: str = ""
    ai_model: str = ""
    ai_timeout_seconds: float = 30.0
    ai_prompt_version: str = "v1"
    ai_daily_request_limit_per_user: int = 50

    media_root: str = "./media"
    media_public_base_url: str = "http://localhost:8080/media"

    learning_language_code: str = "en"
    native_language_code: str = "ru"

    lookup_meanings_page_size: int = Field(default=3, ge=1, le=10)

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def admin_telegram_id_set(self) -> frozenset[int]:
        raw_ids = (part.strip() for part in self.admin_telegram_ids.split(","))
        return frozenset(int(value) for value in raw_ids if value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Три вещи заслуживают внимания. `env_file="../.env"` — `.env` лежит в корне репозитория, а код
запускается из `backend/`; в Docker переменные придут из окружения, и файл просто не будет найден,
что нормально. `@lru_cache` делает `get_settings()` singleton — настройки читаются один раз.
`secret_key` и `postgres_password` без значений по умолчанию: приложение не стартует без них, и это
правильно — лучше падение при старте, чем работа с пустым ключом подписи.

Создайте `backend/app/main.py`:

```python
from fastapi import FastAPI

from app.common.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="English Vocabulary API",
        version="0.1.0",
        docs_url="/docs" if settings.app_debug else None,
        redoc_url=None,
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

Функция-фабрика вместо модуля-уровня `app = FastAPI(...)` пригодится в тестах: там создаётся отдельный
экземпляр приложения с подменёнными зависимостями.

Создайте пустые `__init__.py` в `app/`, `app/common/`, `tests/`:

```bash
touch app/__init__.py app/common/__init__.py tests/__init__.py
```

### Проверка

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

В другом терминале:

```bash
curl -s http://localhost:8000/health
```

Ожидается `{"status":"ok"}`. Откройте `http://localhost:8000/docs` — увидите страницу документации
(она доступна, потому что `APP_DEBUG=true` в `.env`).

Линтеры должны быть чистыми:

```bash
uv run ruff check app
uv run mypy app
```

### Коммит

`feat(backend): add FastAPI skeleton with settings and health endpoint`

---

## Шаг 8. Структурное логирование и correlation ID

### Цель

Каждая строка лога — JSON с идентификатором запроса. По этому идентификатору можно связать запись
в логе API с записью в логе Celery.

### Почему это делается сейчас, а не потом

Когда на неделе 2 сломается обогащение карточки, вопрос будет звучать так: «что произошло именно с
этим словом». Без correlation ID вы будете сопоставлять записи по времени. Добавить логирование
позже технически легко, но к тому моменту вы уже потеряете часы на отладке.

### Файлы

`backend/app/common/logging.py`, `backend/app/common/request_context.py`, правка `main.py`.

### Действия

Создайте `backend/app/common/request_context.py`:

```python
from contextvars import ContextVar
from uuid import uuid4

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def set_correlation_id(value: str | None = None) -> str:
    correlation_id = value or uuid4().hex
    _correlation_id.set(correlation_id)
    return correlation_id


def get_correlation_id() -> str | None:
    return _correlation_id.get()
```

`ContextVar` — механизм Python для данных, привязанных к текущей задаче исполнения. В отличие от
глобальной переменной, значение не утечёт между параллельными запросами: каждая корутина видит своё.

Создайте `backend/app/common/logging.py`:

```python
import json
import logging
import sys
from typing import ClassVar

from app.common.request_context import get_correlation_id

_RESERVED_RECORD_KEYS: frozenset[str] = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


class JsonLogFormatter(logging.Formatter):
    default_time_format: ClassVar[str] = "%Y-%m-%dT%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        correlation_id = get_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id

        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_KEYS:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*, debug: bool) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    for noisy_logger_name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy_logger_name).setLevel(logging.WARNING)
```

Приём с `_RESERVED_RECORD_KEYS` даёт возможность писать так:

```python
logger.info("dictionary lookup finished", extra={"provider": "yandex", "meanings_found": 3})
```

и получить эти поля отдельными ключами JSON, а не склеенными в строку сообщения. Именно так и надо
логировать — раздел 37 правил проекта требует структурных логов.

Добавьте middleware в `main.py`:

```python
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.common.logging import configure_logging
from app.common.request_context import set_correlation_id
from app.common.settings import get_settings

logger = logging.getLogger(__name__)

CORRELATION_ID_HEADER = "X-Correlation-ID"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(debug=settings.app_debug)

    app = FastAPI(
        title="English Vocabulary API",
        version="0.1.0",
        docs_url="/docs" if settings.app_debug else None,
        redoc_url=None,
    )

    @app.middleware("http")
    async def attach_correlation_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = set_correlation_id(request.headers.get(CORRELATION_ID_HEADER))
        started_at = time.perf_counter()

        response = await call_next(request)

        response.headers[CORRELATION_ID_HEADER] = correlation_id
        logger.info(
            "request handled",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

### Проверка

Перезапустите сервер и сделайте запрос:

```bash
curl -si http://localhost:8000/health | grep -i correlation
```

В заголовках ответа должен появиться `x-correlation-id`. В консоли сервера — строка JSON вида:

```json
{"timestamp":"2026-09-21T20:15:03","level":"INFO","logger":"app.main","message":"request handled","correlation_id":"8f2c...","method":"GET","path":"/health","status_code":200,"duration_ms":1.42}
```

Проверьте, что переданный клиентом идентификатор сохраняется:

```bash
curl -si -H "X-Correlation-ID: my-test-id" http://localhost:8000/health | grep -i correlation
```

### Коммит

`feat(backend): add structured logging with correlation id`

---

## Шаг 9. Dockerfile backend и первый `docker-compose`

### Цель

PostgreSQL, Redis и backend поднимаются одной командой.

### Файлы

`backend/Dockerfile`, `backend/.dockerignore`, `infra/docker-compose.yml`.

### Действия

Создайте `backend/Dockerfile`:

```dockerfile
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Зависимости копируются и устанавливаются до копирования кода — тогда слой с библиотеками
переиспользуется, и пересборка после правки кода занимает секунды, а не минуты. `ffmpeg` нужен шагу
32. Файлы `alembic.ini` и `alembic/` появятся на шаге 11; чтобы образ собирался сейчас, временно
закомментируйте две строки с ними и раскомментируйте после шага 11.

Создайте `backend/.dockerignore`:

```text
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
tests/
media/
```

Создайте `infra/docker-compose.yml`:

```yaml
name: vocabulary-app

services:
  postgres:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:8-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis-data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  backend:
    build:
      context: ../backend
    restart: unless-stopped
    env_file: ../.env
    environment:
      POSTGRES_HOST: postgres
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/1
      CELERY_RESULT_BACKEND: redis://redis:6379/2
      MEDIA_ROOT: /app/media
    volumes:
      - ../backend/app:/app/app
      - media-data:/app/media
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

volumes:
  postgres-data:
  redis-data:
  media-data:
```

Монтирование `../backend/app:/app/app` вместе с `--reload` даёт горячую перезагрузку: правите файл на
хосте — процесс в контейнере перезапускается. Для production это переопределяется отдельным файлом
на шаге 68.

Порты PostgreSQL и Redis открыты наружу — это удобно для локальной отладки через `psql` и
`redis-cli`, но в production их публиковать нельзя (шаг 68).

### Проверка

```bash
cd infra
docker compose up --build
```

Дождитесь готовности и в другом терминале:

```bash
curl -s http://localhost:8000/health
docker compose ps
```

Все три сервиса должны быть в состоянии `running`, postgres и redis — `healthy`.

Проверьте доступность БД:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "select version();"
docker compose exec redis redis-cli ping
```

### Коммит

`feat(infra): add backend dockerfile and compose with postgres and redis`

---

## Шаг 10. Подключение PostgreSQL: engine, сессия, `/ready`

### Цель

Приложение открывает соединения к PostgreSQL и Redis, эндпоинт `/ready` честно проверяет их
доступность.

### Разница между `/health` и `/ready`

`/health` отвечает «процесс жив» и не обращается к внешним системам. `/ready` отвечает «могу
обслуживать запросы» и проверяет зависимости. Это разделение нужно оркестратору: контейнер, у которого
на секунду отвалился Redis, не должен перезапускаться, но и трафик ему давать не надо.

### Файлы

`backend/app/common/database.py`, `backend/app/common/redis_client.py`, правка `main.py`.

### Действия

Создайте `backend/app/common/database.py`:

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.common.settings import get_settings


class Base(DeclarativeBase):
    pass


def create_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )


engine: AsyncEngine = create_engine()

session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

Разбор параметров, которые влияют на поведение в бою:

* `pool_pre_ping=True` — перед выдачей соединения из пула проверяется, что оно живо. Спасает от
  ошибок после перезапуска PostgreSQL или разрыва по таймауту;
* `expire_on_commit=False` — после `commit()` объекты остаются читаемыми. Без этого обращение к полю
  после коммита вызовет новый запрос, а в async-коде — исключение `MissingGreenlet`;
* `autoflush=False` — SQLAlchemy не будет отправлять незавершённые изменения перед каждым запросом
  неявно. Так поведение предсказуемее: вы сами решаете, когда `flush`;
* зависимость откатывает транзакцию при исключении, но не коммитит. Коммит — ответственность
  сервиса, как договорились в правилах проекта.

Обратите внимание: в `get_db_session` нет `await session.commit()`. Это сознательно.

Создайте `backend/app/common/redis_client.py`:

```python
from redis.asyncio import Redis, from_url

from app.common.settings import get_settings

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
```

Добавьте в `main.py` управление жизненным циклом и `/ready`:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.common.database import engine
from app.common.redis_client import close_redis_client, get_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("application starting")
    yield
    await engine.dispose()
    await close_redis_client()
    logger.info("application stopped")
```

Передайте `lifespan=lifespan` в конструктор `FastAPI` и добавьте эндпоинт:

```python
    @app.get("/ready", tags=["system"])
    async def ready() -> JSONResponse:
        checks: dict[str, bool] = {}

        try:
            async with engine.connect() as connection:
                await connection.execute(text("select 1"))
            checks["database"] = True
        except Exception:
            logger.exception("database readiness check failed")
            checks["database"] = False

        try:
            await get_redis_client().ping()
            checks["redis"] = True
        except Exception:
            logger.exception("redis readiness check failed")
            checks["redis"] = False

        all_ready = all(checks.values())
        return JSONResponse(
            status_code=status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "ready" if all_ready else "not_ready", "checks": checks},
        )
```

`lifespan` — современная замена устаревшим `@app.on_event("startup")`. Код до `yield` выполняется при
старте, после — при остановке. Здесь мы закрываем пул соединений, чтобы не оставлять «висящие»
сессии в PostgreSQL при перезапуске.

### Проверка

```bash
cd infra
docker compose up --build backend
curl -s http://localhost:8000/ready | python3 -m json.tool
```

Ожидается:

```json
{
    "status": "ready",
    "checks": {
        "database": true,
        "redis": true
    }
}
```

Проверьте деградацию — остановите Redis и повторите запрос:

```bash
docker compose stop redis
curl -si http://localhost:8000/ready | head -1
docker compose start redis
```

Первая строка должна содержать `503 Service Unavailable`, а в теле — `"redis": false`. Это значит,
что проверка настоящая, а не декоративная.

### Коммит

`feat(backend): add database and redis connections with readiness probe`

---

## Шаг 11. Alembic для async-движка и первая миграция

### Цель

Схема БД управляется миграциями. Первая миграция включает расширения PostgreSQL.

### Файлы

`backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/*.py`,
`backend/app/common/models_registry.py`.

### Действия

Инициализируйте Alembic с асинхронным шаблоном:

```bash
cd backend
uv run alembic init -t async alembic
```

Шаблон `async` важен: обычный сгенерирует синхронный `env.py`, который не умеет работать с `asyncpg`.

Откройте `alembic.ini` и удалите строку `sqlalchemy.url = ...` (или оставьте пустой) — URL мы будем
подставлять из настроек, чтобы пароль не лежал в конфиге. Приведите начало файла к такому виду:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s
sqlalchemy.url =
```

`file_template` даёт файлы миграций с датой в имени — история читается по порядку, а не по случайным
хэшам.

Создайте `backend/app/common/models_registry.py` — единое место импорта всех моделей:

```python
from app.common.database import Base

__all__ = ["Base"]
```

По мере появления моделей здесь будут добавляться импорты. Смысл файла: Alembic видит только те
таблицы, чьи классы были импортированы. Забытый импорт означает, что autogenerate «не заметит»
таблицу — или, хуже, предложит её удалить.

Замените содержимое `backend/alembic/env.py`:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.common.models_registry import Base
from app.common.settings import get_settings

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`compare_type=True` заставляет Alembic замечать изменения типов колонок — без него смена
`String(80)` на `String(120)` пройдёт незамеченной.

Создайте первую миграцию вручную (autogenerate для расширений не годится):

```bash
uv run alembic revision -m "enable postgres extensions"
```

Откройте созданный файл в `alembic/versions/` и заполните:

```python
from alembic import op

revision: str = "<оставьте сгенерированное значение>"
down_revision: str | None = None
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
```

`pg_trgm` нужно для поиска опечаток (шаг 34) — оно даёт функцию `similarity()` и индексы для
нечёткого сравнения строк. `uuid-ossp` даёт генерацию UUID на стороне БД.

Раскомментируйте в `backend/Dockerfile` строки копирования `alembic.ini` и `alembic/`, если вы их
закомментировали на шаге 9.

### Проверка

```bash
cd infra
docker compose up -d postgres
cd ../backend
POSTGRES_HOST=localhost uv run alembic upgrade head
POSTGRES_HOST=localhost uv run alembic current
```

Проверьте, что расширения установлены:

```bash
cd ../infra
docker compose exec postgres psql -U vocabulary -d vocabulary \
  -c "select extname from pg_extension order by extname;"
```

В списке должны быть `pg_trgm`, `plpgsql`, `uuid-ossp`. Также появится служебная таблица
`alembic_version` с номером применённой ревизии.

### Коммит

`feat(backend): configure alembic and enable postgres extensions`

---

## Шаг 12. Модели `Language`, `User`, `AuthIdentity`

### Цель

В БД есть таблицы языков, пользователей и внешних идентичностей.

### Ключевое решение об идентификаторах

Следуем модели данных из продуктового плана:

* **UUID** — для сущностей пользователя (`User`, `UserVocabularyItem`, `Collection`, `StudySession`).
  Идентификатор попадает в URL, и UUID не даёт перебирать чужие записи по возрастающему номеру;
* **bigint** — для общего лексикона (`Language`, `Lexeme`, `Meaning`, `Translation`).
  Записей будет много, они шарятся между пользователями, и компактный ключ экономит место в индексах.

Отдельно подчеркну требование безопасности из продуктового плана: **Telegram ID не является
первичным ключом пользователя**. Он живёт в `AuthIdentity.external_user_id`. Это даёт возможность
позже добавить вход через Apple или email, не переделывая схему.

### Файлы

`backend/app/languages/models.py`, `backend/app/users/models.py`, `backend/app/auth/models.py`,
`backend/app/common/mixins.py`, правки `models_registry.py`.

### Действия

Создайте `backend/app/common/mixins.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

`server_default=func.now()` означает, что значение ставит PostgreSQL, а не Python. Это надёжнее:
время будет корректным даже при вставке в обход ORM. `DateTime(timezone=True)` даёт `timestamptz` —
храните время только с зоной, иначе при переносе на сервер в другой зоне получите сдвиг.

Создайте `backend/app/languages/models.py`:

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import Base


class Language(Base):
    __tablename__ = "languages"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
```

Создайте `backend/app/users/models.py`:

```python
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import Base
from app.common.mixins import TimestampMixin


class CefrLevel(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    native_language_id: Mapped[int | None] = mapped_column(
        ForeignKey("languages.id", ondelete="RESTRICT")
    )
    learning_language_id: Mapped[int | None] = mapped_column(
        ForeignKey("languages.id", ondelete="RESTRICT")
    )
    cefr_level: Mapped[CefrLevel | None] = mapped_column(
        SqlEnum(CefrLevel, name="cefr_level", native_enum=True)
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Добавьте недостающие импорты `datetime` и `DateTime` вверху файла.

Поля языков и уровня nullable, потому что пользователь создаётся в момент первой аутентификации,
до onboarding. Факт прохождения onboarding определяется по `onboarding_completed_at` — это надёжнее,
чем проверять заполненность трёх полей, и даёт время события для аналитики.

Создайте `backend/app/auth/models.py`:

```python
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import Base
from app.common.mixins import TimestampMixin


class AuthProvider(StrEnum):
    TELEGRAM = "telegram"


class AuthIdentity(Base, TimestampMixin):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "external_user_id", name="uq_auth_identities_provider_external"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[AuthProvider] = mapped_column(
        SqlEnum(AuthProvider, name="auth_provider", native_enum=True), nullable=False
    )
    external_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
```

Уникальное ограничение на пару `(provider, external_user_id)` — это то, что не даст создать двух
пользователей для одного Telegram-аккаунта. Проверка в коде здесь недостаточна: два одновременных
запроса при первом входе пройдут проверку оба. Ограничение в БД — единственная настоящая защита,
и правила проекта прямо этого требуют.

`ondelete="CASCADE"` на `user_id` означает, что при удалении пользователя его идентичности удалятся
автоматически — понадобится на шаге 59.

Обновите `backend/app/common/models_registry.py`:

```python
from app.auth.models import AuthIdentity
from app.common.database import Base
from app.languages.models import Language
from app.users.models import User

__all__ = ["AuthIdentity", "Base", "Language", "User"]
```

Не забудьте `__init__.py` в новых пакетах:

```bash
cd backend
touch app/languages/__init__.py app/users/__init__.py app/auth/__init__.py
```

Сгенерируйте миграцию:

```bash
POSTGRES_HOST=localhost uv run alembic revision --autogenerate -m "add users languages auth identities"
```

**Откройте сгенерированный файл и прочитайте его.** Убедитесь, что:

* создаются три таблицы и два типа enum (`cefr_level`, `auth_provider`);
* есть уникальные ограничения на `languages.code` и на пару в `auth_identities`;
* в `downgrade()` типы enum удаляются явно. Alembic часто это забывает — добавьте руками:

```python
def downgrade() -> None:
    op.drop_table("auth_identities")
    op.drop_table("users")
    op.drop_table("languages")
    op.execute("DROP TYPE IF EXISTS auth_provider")
    op.execute("DROP TYPE IF EXISTS cefr_level")
```

Без этих двух строк повторный `upgrade` после `downgrade` упадёт с ошибкой «type already exists».
Это самая частая проблема с enum в Alembic.

Примените:

```bash
POSTGRES_HOST=localhost uv run alembic upgrade head
```

### Проверка

```bash
cd infra
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\dt"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\d users"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\d auth_identities"
```

Проверьте обратимость миграции — это стоит делать для каждой миграции, пока данных нет:

```bash
cd ../backend
POSTGRES_HOST=localhost uv run alembic downgrade -1
POSTGRES_HOST=localhost uv run alembic upgrade head
```

Обе команды должны пройти без ошибок.

### Коммит

`feat(backend): add user, language and auth identity models`

---

## Шаг 13. Наполнение таблицы языков

### Цель

В таблице `languages` есть английский и русский.

### Почему миграцией, а не скриптом

Это не пользовательские данные, а справочник, без которого приложение не работает. Значит, он должен
появляться автоматически при развёртывании — иначе на production вы получите пустую таблицу и
сломанный onboarding.

### Действия

```bash
cd backend
uv run alembic revision -m "seed languages"
```

Заполните файл:

```python
from alembic import op
from sqlalchemy import table, column, String, Integer

revision: str = "<сгенерированное значение>"
down_revision: str | None = "<предыдущая ревизия>"

languages_table = table(
    "languages",
    column("id", Integer),
    column("code", String),
    column("name", String),
)

SEEDED_LANGUAGES = [
    {"id": 1, "code": "en", "name": "English"},
    {"id": 2, "code": "ru", "name": "Русский"},
]


def upgrade() -> None:
    op.bulk_insert(languages_table, SEEDED_LANGUAGES)
    op.execute("SELECT setval('languages_id_seq', (SELECT MAX(id) FROM languages))")


def downgrade() -> None:
    op.execute("DELETE FROM languages WHERE code IN ('en', 'ru')")
```

Две тонкости. Конструкция `table(...)` вместо импорта ORM-модели — миграция не должна зависеть от
текущего состояния кода моделей: модель изменится, а старая миграция должна продолжать работать.
Вызов `setval` нужен потому, что при вставке с явными id последовательность не двигается, и следующая
вставка без id попытается использовать `id=1` и упадёт на уникальности.

```bash
POSTGRES_HOST=localhost uv run alembic upgrade head
```

### Проверка

```bash
cd ../infra
docker compose exec postgres psql -U vocabulary -d vocabulary -c "select * from languages;"
```

### Коммит

`feat(backend): seed english and russian languages`

---

## Шаг 14. Валидация Telegram `initData` с тестами

### Цель

Backend умеет проверять подлинность данных, полученных от Telegram Mini App, и отклонять подделки.

### Как это работает

Telegram при открытии Mini App передаёт в клиент строку `initData` — query-строку с полями
пользователя, временем и подписью `hash`. Проверка подписи выглядит так:

1. из строки убирается параметр `hash`;
2. остальные параметры сортируются по имени и склеиваются в строки `key=value` через `\n` —
   получается «data check string»;
3. вычисляется секретный ключ: `HMAC-SHA256(key="WebAppData", message=<токен бота>)`;
4. вычисляется `HMAC-SHA256(key=<секретный ключ из п.3>, message=<data check string>)`;
5. результат в hex сравнивается с `hash` из `initData`.

Дополнительно проверяется свежесть `auth_date` — иначе перехваченная один раз строка будет работать
вечно.

**Этот шаг нельзя упрощать и нельзя откладывать.** Без него любой человек, знающий адрес вашего API,
отправит произвольный Telegram ID и получит доступ к чужому словарю. Именно поэтому в продуктовом
плане отдельно написано «не доверять данным клиента».

### Файлы

`backend/app/auth/telegram.py`, `backend/tests/test_telegram_auth.py`.

### Действия

Создайте `backend/app/auth/telegram.py`:

```python
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class TelegramAuthError(Exception):
    pass


class TelegramInitDataMalformed(TelegramAuthError):
    pass


class TelegramInitDataSignatureInvalid(TelegramAuthError):
    pass


class TelegramInitDataExpired(TelegramAuthError):
    pass


@dataclass(frozen=True, slots=True)
class TelegramUserIdentity:
    telegram_user_id: int
    language_code: str | None
    is_premium: bool


def parse_and_verify_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
) -> TelegramUserIdentity:
    fields = dict(parse_qsl(init_data, strict_parsing=False, keep_blank_values=True))

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise TelegramInitDataMalformed("init data has no hash")

    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise TelegramInitDataSignatureInvalid("init data signature mismatch")

    auth_date_raw = fields.get("auth_date")
    if not auth_date_raw or not auth_date_raw.isdigit():
        raise TelegramInitDataMalformed("init data has no valid auth_date")

    if time.time() - int(auth_date_raw) > max_age_seconds:
        raise TelegramInitDataExpired("init data is too old")

    return _extract_user_identity(fields.get("user"))


def _extract_user_identity(user_field: str | None) -> TelegramUserIdentity:
    if not user_field:
        raise TelegramInitDataMalformed("init data has no user")

    try:
        parsed_user = json.loads(user_field)
    except json.JSONDecodeError as error:
        raise TelegramInitDataMalformed("init data user is not valid json") from error

    telegram_user_id = parsed_user.get("id")
    if not isinstance(telegram_user_id, int):
        raise TelegramInitDataMalformed("init data user has no numeric id")

    language_code = parsed_user.get("language_code")
    return TelegramUserIdentity(
        telegram_user_id=telegram_user_id,
        language_code=language_code if isinstance(language_code, str) else None,
        is_premium=bool(parsed_user.get("is_premium", False)),
    )
```

Четыре детали, каждая из которых важна:

* `hmac.compare_digest` вместо `==` — сравнение за постоянное время, защита от timing-атак;
* `hash` удаляется из словаря **до** построения проверочной строки, иначе подпись никогда не сойдётся;
* сортировка ключей обязательна — порядок в исходной строке не гарантирован;
* из всех данных пользователя мы берём только id, язык и признак premium. Имя, фамилию и username
  не сохраняем — раздел о приватности в продуктовом плане требует хранить минимум.

Создайте `backend/tests/test_telegram_auth.py`:

```python
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.auth.telegram import (
    TelegramInitDataExpired,
    TelegramInitDataMalformed,
    TelegramInitDataSignatureInvalid,
    parse_and_verify_init_data,
)

BOT_TOKEN = "123456:TEST-TOKEN"
MAX_AGE_SECONDS = 86_400


def build_init_data(
    *,
    telegram_user_id: int = 555_000_111,
    auth_date: int | None = None,
    bot_token: str = BOT_TOKEN,
    corrupt_hash: bool = False,
) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAEtest",
        "user": json.dumps(
            {"id": telegram_user_id, "first_name": "Test", "language_code": "ru"},
            separators=(",", ":"),
        ),
    }

    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if corrupt_hash:
        signature = "0" * 64

    return urlencode({**fields, "hash": signature})


def test_valid_init_data_returns_identity() -> None:
    identity = parse_and_verify_init_data(
        build_init_data(),
        bot_token=BOT_TOKEN,
        max_age_seconds=MAX_AGE_SECONDS,
    )

    assert identity.telegram_user_id == 555_000_111
    assert identity.language_code == "ru"


def test_tampered_hash_is_rejected() -> None:
    with pytest.raises(TelegramInitDataSignatureInvalid):
        parse_and_verify_init_data(
            build_init_data(corrupt_hash=True),
            bot_token=BOT_TOKEN,
            max_age_seconds=MAX_AGE_SECONDS,
        )


def test_init_data_signed_with_other_token_is_rejected() -> None:
    with pytest.raises(TelegramInitDataSignatureInvalid):
        parse_and_verify_init_data(
            build_init_data(bot_token="999:OTHER-TOKEN"),
            bot_token=BOT_TOKEN,
            max_age_seconds=MAX_AGE_SECONDS,
        )


def test_modified_user_id_is_rejected() -> None:
    original = build_init_data(telegram_user_id=1)
    tampered = original.replace("%22id%22%3A1", "%22id%22%3A2")

    with pytest.raises(TelegramInitDataSignatureInvalid):
        parse_and_verify_init_data(
            tampered, bot_token=BOT_TOKEN, max_age_seconds=MAX_AGE_SECONDS
        )


def test_expired_init_data_is_rejected() -> None:
    stale_auth_date = int(time.time()) - MAX_AGE_SECONDS - 60

    with pytest.raises(TelegramInitDataExpired):
        parse_and_verify_init_data(
            build_init_data(auth_date=stale_auth_date),
            bot_token=BOT_TOKEN,
            max_age_seconds=MAX_AGE_SECONDS,
        )


def test_init_data_without_hash_is_rejected() -> None:
    with pytest.raises(TelegramInitDataMalformed):
        parse_and_verify_init_data(
            "auth_date=1700000000&user=%7B%22id%22%3A1%7D",
            bot_token=BOT_TOKEN,
            max_age_seconds=MAX_AGE_SECONDS,
        )
```

Тест `test_modified_user_id_is_rejected` — самый показательный: он имитирует именно ту атаку, от
которой мы защищаемся. Атакующий берёт валидную строку и подменяет в ней id пользователя.

### Проверка

```bash
cd backend
uv run pytest tests/test_telegram_auth.py -v
```

Все шесть тестов должны пройти. Если `test_modified_user_id_is_rejected` падает не с ожидаемым
исключением — проверьте, что замена в строке действительно попала в поле `user` (кодирование может
отличаться; выведите `original` и поправьте подстроку).

### Коммит

`feat(backend): add telegram init data verification with tests`

---

## Шаг 15. Выпуск и проверка JWT

### Цель

После проверки `initData` выдаётся собственный токен приложения; защищённые эндпоинты умеют его
проверять и получать пользователя.

### Почему свой токен, а не `initData` каждый раз

`initData` устаревает, его проверка требует пересчёта HMAC на каждом запросе, и он содержит данные
Telegram, которые незачем гонять туда-сюда. Свой JWT решает эти проблемы и — главное — делает
backend независимым от Telegram, как требует продуктовый план: добавление входа через Apple не
затронет ни один защищённый эндпоинт.

### Файлы

`backend/app/auth/tokens.py`, `backend/app/auth/dependencies.py`, `backend/app/auth/repository.py`,
`backend/app/auth/service.py`, `backend/app/common/errors.py`.

### Действия

Создайте `backend/app/common/errors.py`:

```python
class ApplicationError(Exception):
    pass


class EntityNotFoundError(ApplicationError):
    pass


class PermissionDeniedError(ApplicationError):
    pass


class ValidationFailedError(ApplicationError):
    pass


class RateLimitExceededError(ApplicationError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("rate limit exceeded")
```

Это база для всех доменных ошибок. Сервисы выбрасывают их, а не `HTTPException`; превращение
в HTTP-ответы настроим на шаге 61.

Создайте `backend/app/auth/tokens.py`:

```python
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.common.errors import ApplicationError

JWT_ALGORITHM = "HS256"


class InvalidAccessTokenError(ApplicationError):
    pass


def issue_access_token(*, user_id: UUID, secret_key: str, ttl_days: int) -> str:
    issued_at = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(days=ttl_days)).timestamp()),
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def read_user_id_from_access_token(token: str, *, secret_key: str) -> UUID:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as error:
        raise InvalidAccessTokenError("access token is not valid") from error

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise InvalidAccessTokenError("access token has no subject")

    try:
        return UUID(subject)
    except ValueError as error:
        raise InvalidAccessTokenError("access token subject is not a uuid") from error
```

Обратите внимание на `algorithms=[JWT_ALGORITHM]` при декодировании — список алгоритмов указывается
явно. Если этого не сделать, появляется классическая уязвимость: злоумышленник присылает токен
с `alg: none` или подменяет алгоритм.

Создайте `backend/app/auth/repository.py`:

```python
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthIdentity, AuthProvider
from app.users.models import User


class AuthIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_user_by_external_id(
        self, provider: AuthProvider, external_user_id: str
    ) -> User | None:
        statement = (
            select(User)
            .join(AuthIdentity, AuthIdentity.user_id == User.id)
            .where(
                AuthIdentity.provider == provider,
                AuthIdentity.external_user_id == external_user_id,
            )
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def create_user_with_identity(
        self, provider: AuthProvider, external_user_id: str
    ) -> User:
        user = User()
        self._session.add(user)
        await self._session.flush()

        self._session.add(
            AuthIdentity(
                user_id=user.id,
                provider=provider,
                external_user_id=external_user_id,
            )
        )
        await self._session.flush()
        return user

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)
```

Создайте `backend/app/auth/service.py`:

```python
import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthProvider
from app.auth.repository import AuthIdentityRepository
from app.auth.telegram import parse_and_verify_init_data
from app.auth.tokens import issue_access_token
from app.common.settings import Settings
from app.users.models import User

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    access_token: str
    user: User
    is_new_user: bool


class TelegramAuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._repository = AuthIdentityRepository(session)

    async def authenticate(self, init_data: str) -> AuthenticatedSession:
        identity = parse_and_verify_init_data(
            init_data,
            bot_token=self._settings.telegram_bot_token,
            max_age_seconds=self._settings.telegram_auth_max_age_seconds,
        )
        external_user_id = str(identity.telegram_user_id)

        user = await self._repository.find_user_by_external_id(
            AuthProvider.TELEGRAM, external_user_id
        )
        is_new_user = user is None

        if user is None:
            user = await self._create_user_handling_race(external_user_id)
            is_new_user = user is not None and is_new_user

        await self._session.commit()

        logger.info(
            "telegram authentication succeeded",
            extra={"user_id": str(user.id), "is_new_user": is_new_user},
        )

        return AuthenticatedSession(
            access_token=issue_access_token(
                user_id=user.id,
                secret_key=self._settings.secret_key,
                ttl_days=self._settings.access_token_ttl_days,
            ),
            user=user,
            is_new_user=is_new_user,
        )

    async def _create_user_handling_race(self, external_user_id: str) -> User:
        try:
            return await self._repository.create_user_with_identity(
                AuthProvider.TELEGRAM, external_user_id
            )
        except IntegrityError:
            await self._session.rollback()
            existing_user = await self._repository.find_user_by_external_id(
                AuthProvider.TELEGRAM, external_user_id
            )
            if existing_user is None:
                raise
            return existing_user
```

Метод `_create_user_handling_race` обрабатывает реальный сценарий: Mini App при первом открытии
может отправить два запроса аутентификации почти одновременно. Уникальное ограничение из шага 12
не даст создать дубль, а мы вместо ошибки 500 подхватываем уже созданного пользователя.

Создайте `backend/app/auth/dependencies.py`:

```python
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repository import AuthIdentityRepository
from app.auth.tokens import InvalidAccessTokenError, read_user_id_from_access_token
from app.common.database import get_db_session
from app.common.settings import Settings, get_settings
from app.users.models import User

bearer_scheme = HTTPBearer(auto_error=True)

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: DbSession,
    settings: AppSettings,
) -> User:
    try:
        user_id = read_user_id_from_access_token(
            credentials.credentials, secret_key=settings.secret_key
        )
    except InvalidAccessTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    user = await AuthIdentityRepository(session).get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
```

Здесь `HTTPException` допустим: это граница HTTP, а не бизнес-логика. Смысл проверки существования
пользователя в БД — токен удалённого аккаунта должен перестать работать немедленно.

Псевдонимы `DbSession`, `AppSettings`, `CurrentUser` избавят вас от повторения громоздких
`Annotated[...]` в каждом эндпоинте.

### Проверка

Быстрая проверка выпуска и чтения токена:

```bash
cd backend
uv run python -c "
from uuid import uuid4
from app.auth.tokens import issue_access_token, read_user_id_from_access_token
user_id = uuid4()
token = issue_access_token(user_id=user_id, secret_key='test-secret', ttl_days=1)
print(token[:40], '...')
assert read_user_id_from_access_token(token, secret_key='test-secret') == user_id
print('token roundtrip ok')
"
```

Проверьте, что токен с другим ключом отклоняется:

```bash
uv run python -c "
from uuid import uuid4
from app.auth.tokens import InvalidAccessTokenError, issue_access_token, read_user_id_from_access_token
token = issue_access_token(user_id=uuid4(), secret_key='real', ttl_days=1)
try:
    read_user_id_from_access_token(token, secret_key='fake')
    print('FAIL: forged token accepted')
except InvalidAccessTokenError:
    print('forged token rejected ok')
"
```

### Коммит

`feat(backend): issue and verify application access tokens`

---

## Шаг 16. Эндпоинты `auth/telegram`, `users/me`, `languages`

### Цель

Первые три группы эндпоинтов работают и видны в `/docs`.

Полный контракт — в [08-api-reference.md](08-api-reference.md), здесь реализация.

### Файлы

`backend/app/auth/{schemas.py,router.py}`, `backend/app/users/{schemas.py,service.py,router.py}`,
`backend/app/languages/{schemas.py,router.py}`, правка `main.py`.

### Действия

`backend/app/auth/schemas.py`:

```python
from pydantic import BaseModel, ConfigDict, Field

from app.users.schemas import UserResponse


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=4096)


class AuthTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: str = "bearer"
    user: UserResponse
```

Ограничение `max_length=4096` на `init_data` — это защита от попытки положить сервер большим телом
запроса. Такие лимиты ставятся на каждое строковое поле; раздел безопасности продуктового плана
требует этого явно.

`backend/app/users/schemas.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.users.models import CefrLevel


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    native_language_id: int | None
    learning_language_id: int | None
    cefr_level: CefrLevel | None
    onboarding_completed_at: datetime | None


class UserOnboardingUpdate(BaseModel):
    native_language_id: int
    learning_language_id: int
    cefr_level: CefrLevel
```

`UserOnboardingUpdate` требует все три поля: onboarding — атомарное событие, частично его завершить
нельзя. Это пример правила «не переиспользовать одну схему для create/update/read».

`backend/app/auth/router.py`:

```python
from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import AppSettings, DbSession
from app.auth.schemas import AuthTokenResponse, TelegramAuthRequest
from app.auth.service import TelegramAuthService
from app.auth.telegram import TelegramAuthError
from app.users.schemas import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=AuthTokenResponse)
async def authenticate_via_telegram(
    request: TelegramAuthRequest,
    session: DbSession,
    settings: AppSettings,
) -> AuthTokenResponse:
    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram authentication is not configured",
        )

    try:
        authenticated = await TelegramAuthService(session, settings).authenticate(
            request.init_data
        )
    except TelegramAuthError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram init data is not valid",
        ) from error

    return AuthTokenResponse(
        access_token=authenticated.access_token,
        user=UserResponse.model_validate(authenticated.user),
    )
```

Важная деталь безопасности: клиенту возвращается одинаковое сообщение для всех причин отказа —
неверная подпись, истёкшее время, отсутствие пользователя. Подробная причина уходит в лог. Различать
случаи наружу — значит помогать подбирать валидную подпись.

`backend/app/users/service.py`:

```python
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import ValidationFailedError
from app.languages.models import Language
from app.users.models import User
from app.users.schemas import UserOnboardingUpdate


class UserProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def complete_onboarding(self, user: User, update: UserOnboardingUpdate) -> User:
        await self._ensure_languages_exist(update)

        if update.native_language_id == update.learning_language_id:
            raise ValidationFailedError("native and learning languages must differ")

        user.native_language_id = update.native_language_id
        user.learning_language_id = update.learning_language_id
        user.cefr_level = update.cefr_level
        user.onboarding_completed_at = user.onboarding_completed_at or datetime.now(UTC)

        await self._session.commit()
        return user

    async def _ensure_languages_exist(self, update: UserOnboardingUpdate) -> None:
        requested_ids = {update.native_language_id, update.learning_language_id}
        result = await self._session.execute(
            select(Language.id).where(Language.id.in_(requested_ids))
        )
        found_ids = set(result.scalars().all())

        missing_ids = requested_ids - found_ids
        if missing_ids:
            raise ValidationFailedError(f"unknown language ids: {sorted(missing_ids)}")
```

Сохранение `onboarding_completed_at` через `or` делает операцию идемпотентной: повторный вызов
изменит языки, но не перепишет момент первого прохождения — это нужно для честной аналитики.

`backend/app/users/router.py`:

```python
from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import CurrentUser, DbSession
from app.common.errors import ValidationFailedError
from app.users.schemas import UserOnboardingUpdate, UserResponse
from app.users.service import UserProfileService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_current_user_profile(
    update: UserOnboardingUpdate,
    user: CurrentUser,
    session: DbSession,
) -> UserResponse:
    try:
        updated_user = await UserProfileService(session).complete_onboarding(user, update)
    except ValidationFailedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    return UserResponse.model_validate(updated_user)
```

`backend/app/languages/schemas.py` и `router.py`:

```python
from pydantic import BaseModel, ConfigDict


class LanguageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
```

```python
from fastapi import APIRouter
from sqlalchemy import select

from app.auth.dependencies import DbSession
from app.languages.models import Language
from app.languages.schemas import LanguageResponse

router = APIRouter(prefix="/languages", tags=["languages"])


@router.get("", response_model=list[LanguageResponse])
async def list_languages(session: DbSession) -> list[LanguageResponse]:
    result = await session.execute(select(Language).order_by(Language.name))
    return [LanguageResponse.model_validate(language) for language in result.scalars()]
```

Это единственный случай, где запрос допустим прямо в роутере: один `select` справочника без условий
и без бизнес-правил. Заводить репозиторий и сервис ради него — та самая избыточная абстракция,
от которой предостерегают правила проекта. Как только появится фильтрация или кэширование — вынесем.

Подключите роутеры в `main.py`:

```python
from app.auth.router import router as auth_router
from app.languages.router import router as languages_router
from app.users.router import router as users_router

# внутри create_app(), перед return app:
    app.include_router(auth_router, prefix=settings.api_base_path)
    app.include_router(users_router, prefix=settings.api_base_path)
    app.include_router(languages_router, prefix=settings.api_base_path)
```

Добавьте CORS — Mini App будет обращаться к API с другого источника:

```python
from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "local" else [settings.mini_app_url],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    )
```

В production источник ровно один — адрес Mini App. `allow_origins=["*"]` только локально.

### Проверка

Перезапустите backend и откройте `http://localhost:8000/docs` — должны быть видны все пять
эндпоинтов.

Список языков доступен без токена:

```bash
curl -s http://localhost:8000/api/v1/languages | python3 -m json.tool
```

Защищённый эндпоинт без токена отвечает 403, с мусорным токеном — 401:

```bash
curl -si http://localhost:8000/api/v1/users/me | head -1
curl -si -H "Authorization: Bearer garbage" http://localhost:8000/api/v1/users/me | head -1
```

Полная проверка аутентификации потребует настоящей строки `initData`, которая появится на шаге 20.
Чтобы проверить сейчас, сгенерируйте её тем же кодом, что в тесте:

```bash
cd backend
uv run python -c "
import sys; sys.path.insert(0, 'tests')
from test_telegram_auth import build_init_data
print(build_init_data(bot_token='<ВАШ_ТОКЕН_БОТА>'))
"
```

Затем:

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/telegram \
  -H "Content-Type: application/json" \
  -d '{"init_data":"<вставьте_строку>"}' | python3 -m json.tool
```

Вы получите `access_token` и объект пользователя. Проверьте, что запись создалась:

```bash
cd infra
docker compose exec postgres psql -U vocabulary -d vocabulary \
  -c "select u.id, u.cefr_level, a.provider, a.external_user_id from users u join auth_identities a on a.user_id = u.id;"
```

Затем с полученным токеном:

```bash
TOKEN="<access_token>"
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/users/me | python3 -m json.tool

curl -s -X PATCH http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"native_language_id":2,"learning_language_id":1,"cefr_level":"A2"}' | python3 -m json.tool
```

Во втором ответе должно появиться непустое `onboarding_completed_at`. Проверьте и отказ:
одинаковые языки должны дать 422.

### Коммит

`feat(backend): add auth, user profile and languages endpoints`

---

## Шаг 17. Celery: приложение, worker, проверочная задача

### Цель

Worker запущен отдельным контейнером, умеет выполнять задачи и обращаться к БД.

### Файлы

`backend/app/common/celery_app.py`, `backend/app/common/task_runtime.py`,
правка `infra/docker-compose.yml`.

### Действия

Создайте `backend/app/common/celery_app.py`:

```python
from celery import Celery

from app.common.logging import configure_logging
from app.common.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "vocabulary",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.enrichment.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=100,
    task_time_limit=180,
    task_soft_time_limit=150,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

configure_logging(debug=settings.app_debug)
```

Каждый параметр здесь решает конкретную проблему:

* `task_acks_late=True` — сообщение подтверждается после выполнения, а не при получении. Если worker
  упал посреди обогащения, задача вернётся в очередь;
* `task_reject_on_worker_lost=True` — то же при потере worker;
* `task_time_limit` / `task_soft_time_limit` — обогащение делает три внешних запроса; если провайдер
  «подвиснет», задача не должна держать worker вечно. Soft-лимит даёт шанс завершиться корректно;
* `worker_prefetch_multiplier=1` — worker берёт по одной задаче. Наши задачи долгие и ждут сети,
  забирать их пачкой бессмысленно;
* `worker_max_tasks_per_child=100` — перезапуск процесса, страховка от утечек памяти.

`include=["app.enrichment.tasks"]` регистрирует модуль задач. Файл появится на шаге 38 — пока создайте
его пустым, иначе worker не стартует:

```bash
mkdir -p backend/app/enrichment
touch backend/app/enrichment/__init__.py backend/app/enrichment/tasks.py
```

Создайте `backend/app/common/task_runtime.py` — мост между синхронным Celery и асинхронным кодом:

```python
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.settings import get_settings

T = TypeVar("T")


def run_async_task(coroutine_factory: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coroutine_factory())


@asynccontextmanager
async def task_db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()
```

Почему здесь создаётся **отдельный** engine, а не используется общий из `database.py`: объект engine
привязан к тому event loop, в котором был создан. `asyncio.run` создаёт новый loop на каждый вызов,
поэтому переиспользование общего engine приводит к зависаниям, которые крайне трудно отлаживать.
Ценой лишнего подключения мы получаем предсказуемость.

Добавьте проверочную задачу в `backend/app/enrichment/tasks.py` (позже заменим настоящей):

```python
import logging

from sqlalchemy import func, select

from app.common.celery_app import celery_app
from app.common.task_runtime import run_async_task, task_db_session
from app.users.models import User

logger = logging.getLogger(__name__)


@celery_app.task(name="system.count_users")
def count_users() -> int:
    return run_async_task(_count_users)


async def _count_users() -> int:
    async with task_db_session() as session:
        result = await session.execute(select(func.count()).select_from(User))
        total = result.scalar_one()
    logger.info("counted users", extra={"total_users": total})
    return total
```

Обратите внимание на разделение: задача Celery — три строки, вся логика в обычной async-функции,
которую можно вызвать из теста без брокера. Это требование раздела 29 правил проекта, и оно же делает
код тестируемым.

Добавьте сервис worker в `infra/docker-compose.yml`:

```yaml
  celery-worker:
    build:
      context: ../backend
    restart: unless-stopped
    env_file: ../.env
    environment:
      POSTGRES_HOST: postgres
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/1
      CELERY_RESULT_BACKEND: redis://redis:6379/2
      MEDIA_ROOT: /app/media
    volumes:
      - ../backend/app:/app/app
      - media-data:/app/media
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command:
      - celery
      - -A
      - app.common.celery_app:celery_app
      - worker
      - --loglevel=info
      - --concurrency=2
```

`--concurrency=2` — два параллельных процесса. Для одного пользователя этого более чем достаточно,
а раздел безопасности продуктового плана прямо требует ограничивать concurrency: без лимита пачка
задач обогащения может исчерпать и пул соединений к БД, и суточный бюджет AI.

### Проверка

```bash
cd infra
docker compose up -d --build
docker compose logs -f celery-worker
```

В логах должна появиться строка `celery@... ready.` и список зарегистрированных задач, включающий
`system.count_users`.

Поставьте задачу и посмотрите результат:

```bash
docker compose exec backend python -c "
from app.enrichment.tasks import count_users
result = count_users.delay()
print('task id:', result.id)
print('result:', result.get(timeout=20))
"
```

Вернётся число пользователей, а в логах worker появится JSON-запись с полем `total_users`. Это
подтверждает три вещи сразу: брокер работает, worker видит код, и мост к async-БД функционирует.

Убедитесь, что задачи действительно идут через Redis:

```bash
docker compose exec redis redis-cli -n 1 keys '*'
```

### Коммит

`feat(backend): add celery application and worker service`

---

## Шаг 18. Telegram-бот с кнопкой запуска Mini App

### Цель

`/start` присылает кнопку, открывающую Mini App.

### Файлы

`bot/pyproject.toml`, `bot/app/main.py`, `bot/Dockerfile`, правка `docker-compose.yml`.

### Действия

`bot/pyproject.toml`:

```toml
[project]
name = "vocabulary-bot"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "aiogram>=3.17.0",
    "pydantic-settings>=2.8.0",
]

[dependency-groups]
dev = ["ruff>=0.9.0", "mypy>=1.15.0"]

[tool.ruff]
line-length = 100
target-version = "py313"
```

```bash
cd bot
uv sync
```

`bot/app/settings.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    telegram_bot_token: str
    mini_app_url: str
    app_debug: bool = False


@lru_cache
def get_bot_settings() -> BotSettings:
    return BotSettings()
```

`bot/app/main.py`:

```python
import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.settings import get_bot_settings

logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "Привет! Это приложение для изучения английских слов.\n\n"
    "Сохраняй слова, которые встречаешь в книгах, статьях и сериалах — "
    "приложение само подготовит перевод, транскрипцию, определение и пример, "
    "а потом поможет их выучить.\n\n"
    "Нажми кнопку ниже, чтобы начать."
)

HELP_TEXT = "Открой приложение кнопкой ниже. Все слова и темы хранятся внутри него."


def build_mini_app_keyboard(mini_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть приложение",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
        ]
    )


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    settings = get_bot_settings()
    await message.answer(
        WELCOME_TEXT,
        reply_markup=build_mini_app_keyboard(settings.mini_app_url),
    )
    logger.info(
        "start command handled",
        extra={"telegram_user_id": message.from_user.id if message.from_user else None},
    )


@router.message(F.text)
async def handle_any_text(message: Message) -> None:
    settings = get_bot_settings()
    await message.answer(HELP_TEXT, reply_markup=build_mini_app_keyboard(settings.mini_app_url))


async def run_bot() -> None:
    settings = get_bot_settings()
    logging.basicConfig(level=logging.DEBUG if settings.app_debug else logging.INFO)

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    logger.info("bot polling started")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
```

Бот сознательно ничего не знает про API и БД: его единственная задача — быть точкой входа. Вся
логика в Mini App. Это соответствует принципу «backend проектируется независимым от Telegram» и
означает, что при переезде в мобильное приложение бот просто перестанет быть нужен.

Кнопка с `web_app=WebAppInfo(...)` — именно то, что открывает Mini App внутри Telegram и передаёт
`initData`. Обычная ссылка откроет браузер, и аутентификация не сработает.

`bot/Dockerfile`:

```dockerfile
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app

CMD ["python", "-m", "app.main"]
```

Добавьте в `infra/docker-compose.yml`:

```yaml
  telegram-bot:
    build:
      context: ../bot
    restart: unless-stopped
    env_file: ../.env
    volumes:
      - ../bot/app:/app/app
    depends_on:
      - backend
```

### Проверка

Пока Mini App не опубликован, поставьте в `.env` любой https-адрес, например
`MINI_APP_URL=https://example.com`, — кнопка отрисуется, хотя откроет заглушку. Настоящий адрес
появится на шаге 23.

```bash
cd infra
docker compose up -d --build telegram-bot
docker compose logs -f telegram-bot
```

Напишите боту `/start` в Telegram. Должно прийти приветствие с кнопкой «Открыть приложение»,
а в логах — запись `start command handled`.

Если бот не отвечает: убедитесь, что `TELEGRAM_BOT_TOKEN` в `.env` без кавычек и пробелов, и что
нигде не запущена вторая копия бота — Telegram отдаёт обновления только одному потребителю
(в логах при конфликте будет `TelegramConflictError`).

### Коммит

`feat(bot): add telegram bot with mini app launch button`

---

## Шаг 19. Создание Angular-приложения и структуры папок

### Цель

Frontend запускается, структура папок соответствует правилам проекта.

Перед этим шагом прочитайте [02-primer-angular.md](02-primer-angular.md).

### Действия

Из корня репозитория:

```bash
ng new frontend --style=scss --ssr=false --routing --skip-git --package-manager=npm
```

Что означают флаги:

* `--style=scss` — SCSS вместо CSS;
* `--ssr=false` — без серверного рендеринга. Mini App работает внутри Telegram, SSR только добавит
  сложности;
* `--routing` — сразу создать `app.routes.ts`;
* `--skip-git` — репозиторий уже есть;
* standalone и zoneless в Angular 22 включены по умолчанию, отдельных флагов не требуется.

CLI может спросить про AI-инструменты и аналитику — отвечайте по своему усмотрению, на проект это
не влияет.

```bash
cd frontend
npm start
```

Откройте `http://localhost:4200` — увидите стартовую страницу. Остановите сервер.

Создайте структуру папок:

```bash
cd frontend/src/app
mkdir -p core/auth core/telegram core/api
mkdir -p shared/spinner shared/empty-state
mkdir -p features/onboarding features/collections features/vocabulary features/study features/irregular-verbs features/profile
```

Настройте окружения. Создайте `frontend/src/environments/environment.ts`:

```typescript
export const environment = {
  production: false,
  apiBaseUrl: 'http://localhost:8000/api/v1',
} as const;
```

И `frontend/src/environments/environment.production.ts`:

```typescript
export const environment = {
  production: true,
  apiBaseUrl: '/api/v1',
} as const;
```

В production frontend и backend за одним Nginx, поэтому относительный путь — и никаких проблем с CORS.

Подключите замену файла при production-сборке. В `frontend/angular.json` в
`projects.frontend.architect.build.configurations.production` добавьте:

```json
"fileReplacements": [
  {
    "replace": "src/environments/environment.ts",
    "with": "src/environments/environment.production.ts"
  }
]
```

Включите строгость TypeScript. В `frontend/tsconfig.json` в `compilerOptions` убедитесь, что есть:

```json
"strict": true,
"noImplicitOverride": true,
"noPropertyAccessFromIndexSignature": true,
"noImplicitReturns": true,
"noFallthroughCasesInSwitch": true,
"noUnusedLocals": true,
```

а в `angularCompilerOptions`:

```json
"strictTemplates": true,
"strictInjectionParameters": true,
"typeCheckHostBindings": true
```

`strictTemplates` проверяет типы внутри HTML — это ловит опечатки в шаблонах на этапе сборки,
а не в рантайме. Для проекта с большим числом экранов это очень заметная экономия времени.

Включите привязку параметров маршрута в `frontend/src/app/app.config.ts`:

```typescript
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(),
  ],
};
```

Добавьте базовые токены дизайна в `frontend/src/styles.scss`:

```scss
:root {
  --color-background: var(--tg-theme-bg-color, #ffffff);
  --color-surface: var(--tg-theme-secondary-bg-color, #f2f2f7);
  --color-text: var(--tg-theme-text-color, #1c1c1e);
  --color-muted: var(--tg-theme-hint-color, #8e8e93);
  --color-accent: var(--tg-theme-button-color, #2481cc);
  --color-accent-text: var(--tg-theme-button-text-color, #ffffff);
  --color-danger: #e5484d;

  --radius-card: 12px;
  --radius-control: 10px;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;

  --font-body: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  padding: 0;
  min-height: 100vh;
  font-family: var(--font-body);
  background: var(--color-background);
  color: var(--color-text);
  -webkit-font-smoothing: antialiased;
}

button {
  font-family: inherit;
}
```

Приём с `var(--tg-theme-bg-color, #ffffff)` — это ключ к тому, чтобы приложение выглядело родным
внутри Telegram: клиент подставляет свои переменные темы, а наши значения после запятой работают как
запасные при открытии в обычном браузере. Тёмная тема получается бесплатно.

### Проверка

```bash
cd frontend
npm start
npx tsc --noEmit
npm run build
```

Все три команды должны завершиться без ошибок. `npm run build` создаст `dist/`.

### Коммит

`feat(frontend): bootstrap angular application with project structure`

---

## Шаг 20. Мост к Telegram WebApp и вход в приложение

### Цель

Приложение получает `initData` из Telegram, обменивает его на токен, хранит токен и подставляет
в запросы.

### Файлы

`frontend/src/app/core/telegram/telegram-web-app-bridge.ts`,
`frontend/src/app/core/auth/{auth-api.ts,auth-session-store.ts,auth-interceptor.ts,onboarding-guard.ts}`,
`frontend/src/app/core/auth/models/*.ts`, правки `index.html`, `app.config.ts`, `app.ts`.

### Действия

Подключите скрипт Telegram в `frontend/src/index.html` — он обязателен и должен идти до загрузки
приложения:

```html
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <title>English Vocabulary</title>
    <base href="/" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <link rel="icon" type="image/x-icon" href="favicon.ico" />
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
  </head>
  <body>
    <app-root></app-root>
  </body>
</html>
```

Установите типы Telegram WebApp как dev-зависимость:

```bash
cd frontend
npm install --save-dev @types/telegram-web-app
```

Это единственная добавленная зависимость, и она не попадает в бандл — только типы. Оборачивать
Telegram SDK сторонней библиотекой не нужно: нам требуются четыре метода, и своя обёртка честнее.

Создайте `frontend/src/app/core/telegram/telegram-web-app-bridge.ts`:

```typescript
import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class TelegramWebAppBridge {
  private get webApp(): WebApp | undefined {
    return window.Telegram?.WebApp;
  }

  get isRunningInsideTelegram(): boolean {
    return Boolean(this.webApp?.initData);
  }

  get initData(): string | null {
    return this.webApp?.initData || null;
  }

  get colorScheme(): 'light' | 'dark' {
    return this.webApp?.colorScheme ?? 'light';
  }

  markReady(): void {
    this.webApp?.ready();
    this.webApp?.expand();
  }

  showBackButton(onClick: () => void): void {
    const backButton = this.webApp?.BackButton;
    if (!backButton) {
      return;
    }
    backButton.onClick(onClick);
    backButton.show();
  }

  hideBackButton(): void {
    this.webApp?.BackButton.hide();
  }

  notifyHapticSuccess(): void {
    this.webApp?.HapticFeedback.notificationOccurred('success');
  }

  notifyHapticError(): void {
    this.webApp?.HapticFeedback.notificationOccurred('error');
  }
}
```

Все обращения через `?.` не случайны: в обычном браузере `window.Telegram` отсутствует, и приложение
должно продолжать работать — иначе вы не сможете разрабатывать интерфейс без Telegram.

Создайте модели контрактов. `frontend/src/app/core/auth/models/authenticated-session.ts`:

```typescript
import { UserProfile } from './user-profile';

export interface AuthenticatedSession {
  readonly access_token: string;
  readonly token_type: string;
  readonly user: UserProfile;
}
```

`frontend/src/app/core/auth/models/user-profile.ts`:

```typescript
export type CefrLevel = 'A1' | 'A2' | 'B1' | 'B2' | 'C1' | 'C2';

export interface UserProfile {
  readonly id: string;
  readonly native_language_id: number | null;
  readonly learning_language_id: number | null;
  readonly cefr_level: CefrLevel | null;
  readonly onboarding_completed_at: string | null;
}
```

Поля названы как в API — `snake_case`. Это осознанный выбор: переименование добавило бы слой
преобразования без выгоды. Тип `CefrLevel` как union литералов вместо `string` — требование правил
проекта, и оно ловит опечатки на этапе компиляции.

Создайте `frontend/src/app/core/auth/auth-api.ts`:

```typescript
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { AuthenticatedSession } from './models/authenticated-session';
import { CefrLevel, UserProfile } from './models/user-profile';

export interface OnboardingRequest {
  readonly native_language_id: number;
  readonly learning_language_id: number;
  readonly cefr_level: CefrLevel;
}

@Injectable({ providedIn: 'root' })
export class AuthApi {
  private readonly http = inject(HttpClient);

  authenticateWithTelegram(initData: string): Observable<AuthenticatedSession> {
    return this.http.post<AuthenticatedSession>(`${environment.apiBaseUrl}/auth/telegram`, {
      init_data: initData,
    });
  }

  getCurrentUser(): Observable<UserProfile> {
    return this.http.get<UserProfile>(`${environment.apiBaseUrl}/users/me`);
  }

  completeOnboarding(request: OnboardingRequest): Observable<UserProfile> {
    return this.http.patch<UserProfile>(`${environment.apiBaseUrl}/users/me`, request);
  }
}
```

Создайте `frontend/src/app/core/auth/auth-session-store.ts`:

```typescript
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { TelegramWebAppBridge } from '../telegram/telegram-web-app-bridge';
import { AuthApi } from './auth-api';
import { UserProfile } from './models/user-profile';

const ACCESS_TOKEN_STORAGE_KEY = 'vocabulary.accessToken';

export type AuthStatus = 'idle' | 'authenticating' | 'authenticated' | 'failed';

@Injectable({ providedIn: 'root' })
export class AuthSessionStore {
  private readonly authApi = inject(AuthApi);
  private readonly telegram = inject(TelegramWebAppBridge);

  private readonly token = signal<string | null>(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY));
  private readonly currentUser = signal<UserProfile | null>(null);
  private readonly status = signal<AuthStatus>('idle');

  readonly accessToken = this.token.asReadonly();
  readonly user = this.currentUser.asReadonly();
  readonly authStatus = this.status.asReadonly();

  readonly isOnboardingCompleted = computed(
    () => this.currentUser()?.onboarding_completed_at !== null,
  );

  async authenticate(): Promise<void> {
    if (this.status() === 'authenticating') {
      return;
    }
    this.status.set('authenticating');

    try {
      const restored = await this.tryRestoreExistingSession();
      if (restored) {
        return;
      }

      const initData = this.telegram.initData;
      if (!initData) {
        this.status.set('failed');
        return;
      }

      const session = await firstValueFrom(this.authApi.authenticateWithTelegram(initData));
      this.persistToken(session.access_token);
      this.currentUser.set(session.user);
      this.status.set('authenticated');
    } catch {
      this.clearToken();
      this.status.set('failed');
    }
  }

  applyUpdatedUser(user: UserProfile): void {
    this.currentUser.set(user);
  }

  clearSession(): void {
    this.clearToken();
    this.currentUser.set(null);
    this.status.set('idle');
  }

  private async tryRestoreExistingSession(): Promise<boolean> {
    if (!this.token()) {
      return false;
    }
    try {
      const user = await firstValueFrom(this.authApi.getCurrentUser());
      this.currentUser.set(user);
      this.status.set('authenticated');
      return true;
    } catch {
      this.clearToken();
      return false;
    }
  }

  private persistToken(token: string): void {
    localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
    this.token.set(token);
  }

  private clearToken(): void {
    localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    this.token.set(null);
  }
}
```

Логика входа устроена так: если токен уже сохранён, пробуем им воспользоваться; если он истёк или
пользователь удалён — молча получаем новый через `initData`. Для пользователя это означает, что
повторное открытие Mini App происходит без задержки на аутентификацию.

Состояние `status` — явно перечисленные варианты (`idle`/`authenticating`/`authenticated`/`failed`),
как требует раздел 17 правил проекта. Два булевых флага вместо этого неизбежно дают невозможные
комбинации.

Создайте `frontend/src/app/core/auth/auth-interceptor.ts`:

```typescript
import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { AuthSessionStore } from './auth-session-store';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const token = inject(AuthSessionStore).accessToken();
  if (!token) {
    return next(request);
  }
  return next(request.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};
```

Создайте `frontend/src/app/core/auth/onboarding-guard.ts`:

```typescript
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthSessionStore } from './auth-session-store';

export const onboardingGuard: CanActivateFn = () => {
  const session = inject(AuthSessionStore);
  const router = inject(Router);

  if (session.authStatus() !== 'authenticated') {
    return false;
  }
  return session.isOnboardingCompleted() ? true : router.createUrlTree(['/onboarding']);
};
```

Подключите перехватчик в `app.config.ts`:

```typescript
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { authInterceptor } from './core/auth/auth-interceptor';

// в providers:
provideHttpClient(withInterceptors([authInterceptor])),
```

Сделайте корневой компонент точкой входа. `frontend/src/app/app.ts`:

```typescript
import { Component, OnInit, inject } from '@angular/core';
import { Router, RouterOutlet } from '@angular/router';

import { AuthSessionStore } from './core/auth/auth-session-store';
import { TelegramWebAppBridge } from './core/telegram/telegram-web-app-bridge';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  private readonly telegram = inject(TelegramWebAppBridge);
  private readonly router = inject(Router);
  protected readonly session = inject(AuthSessionStore);

  async ngOnInit(): Promise<void> {
    this.telegram.markReady();
    await this.session.authenticate();

    if (this.session.authStatus() === 'authenticated' && !this.session.isOnboardingCompleted()) {
      await this.router.navigate(['/onboarding']);
    }
  }
}
```

`frontend/src/app/app.html`:

```html
@switch (session.authStatus()) {
  @case ('authenticated') {
    <main class="app-shell">
      <router-outlet />
    </main>
  }
  @case ('failed') {
    <div class="app-message">
      <h1 class="app-message__title">Не удалось войти</h1>
      <p class="app-message__text">
        Откройте приложение через Telegram — кнопкой «Открыть приложение» в чате с ботом.
      </p>
    </div>
  }
  @default {
    <div class="app-message">
      <p class="app-message__text">Загружаем…</p>
    </div>
  }
}
```

`frontend/src/app/app.scss`:

```scss
.app-shell {
  display: block;
  min-height: 100vh;
  padding: var(--space-4);
}

.app-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: var(--space-5);
  text-align: center;

  &__title {
    margin: 0 0 var(--space-3);
    font-size: 20px;
  }

  &__text {
    margin: 0;
    color: var(--color-muted);
  }
}
```

`markReady()` вызывается первым делом: он сообщает Telegram, что приложение отрисовано, и убирает
загрузочный индикатор клиента.

### Проверка

Полноценно этот шаг проверяется только внутри Telegram, поэтому окончательная проверка — на шаге 23.
Сейчас убедитесь, что в обычном браузере приложение показывает понятное сообщение, а не белый экран:

```bash
cd frontend
npm start
```

Откройте `http://localhost:4200`. Ожидается экран «Не удалось войти» с подсказкой — это правильное
поведение вне Telegram.

В консоли браузера не должно быть исключений. Проверьте в Network, что запрос
`POST /api/v1/auth/telegram` не отправлялся (нет `initData`), а сообщение появилось сразу.

### Коммит

`feat(frontend): add telegram bridge and authentication session store`

---

## Шаг 21. Слой API на фронте и типы контрактов

### Цель

Есть общий модуль нормализации ошибок API и сервис языков. Компоненты не будут разбирать
HTTP-ошибки самостоятельно.

### Файлы

`frontend/src/app/core/api/api-error.ts`, `frontend/src/app/core/api/async-state.ts`,
`frontend/src/app/features/onboarding/languages-api.ts`.

### Действия

Создайте `frontend/src/app/core/api/api-error.ts`:

```typescript
import { HttpErrorResponse } from '@angular/common/http';

export type ApiErrorKind =
  | 'network'
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'validation'
  | 'rate_limited'
  | 'server'
  | 'unknown';

export interface ApiError {
  readonly kind: ApiErrorKind;
  readonly message: string;
  readonly retryAfterSeconds: number | null;
}

const USER_MESSAGES: Record<ApiErrorKind, string> = {
  network: 'Нет соединения. Проверьте интернет и попробуйте снова.',
  unauthorized: 'Сессия истекла. Откройте приложение заново.',
  forbidden: 'Недостаточно прав для этого действия.',
  not_found: 'Запись не найдена.',
  validation: 'Проверьте введённые данные.',
  rate_limited: 'Слишком много запросов. Подождите немного.',
  server: 'Что-то пошло не так на сервере. Попробуйте позже.',
  unknown: 'Неизвестная ошибка. Попробуйте позже.',
};

export function toApiError(error: unknown): ApiError {
  if (!(error instanceof HttpErrorResponse)) {
    return { kind: 'unknown', message: USER_MESSAGES.unknown, retryAfterSeconds: null };
  }

  const kind = resolveKind(error.status);
  const retryAfterHeader = error.headers.get('Retry-After');

  return {
    kind,
    message: extractServerMessage(error) ?? USER_MESSAGES[kind],
    retryAfterSeconds: retryAfterHeader ? Number(retryAfterHeader) : null,
  };
}

function resolveKind(status: number): ApiErrorKind {
  if (status === 0) return 'network';
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 422) return 'validation';
  if (status === 429) return 'rate_limited';
  if (status >= 500) return 'server';
  return 'unknown';
}

function extractServerMessage(error: HttpErrorResponse): string | null {
  const body: unknown = error.error;
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') {
      return detail;
    }
  }
  return null;
}
```

Функция принимает `unknown`, а не `any` — правила проекта требуют именно этого для внешних данных,
и здесь тип сужается сразу через `instanceof` и проверки свойств. Компоненты получают готовый
`ApiError` с текстом для пользователя и никогда не смотрят на коды статусов.

Создайте `frontend/src/app/core/api/async-state.ts`:

```typescript
import { ApiError } from './api-error';

export type AsyncState<T> =
  | { readonly status: 'idle' }
  | { readonly status: 'loading' }
  | { readonly status: 'success'; readonly data: T }
  | { readonly status: 'error'; readonly error: ApiError };

export const idleState = { status: 'idle' } as const;
export const loadingState = { status: 'loading' } as const;

export function successState<T>(data: T): AsyncState<T> {
  return { status: 'success', data };
}

export function errorState<T>(error: ApiError): AsyncState<T> {
  return { status: 'error', error };
}
```

Это discriminated union — тип, который делает невозможные состояния невыразимыми. С тремя отдельными
сигналами (`data`, `loading`, `error`) всегда можно получить «загружается и при этом ошибка»;
здесь — нет. Раздел 17 правил проекта требует именно явной модели async-состояний.

Создайте `frontend/src/app/features/onboarding/languages-api.ts`:

```typescript
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface Language {
  readonly id: number;
  readonly code: string;
  readonly name: string;
}

@Injectable({ providedIn: 'root' })
export class LanguagesApi {
  private readonly http = inject(HttpClient);

  listLanguages(): Observable<Language[]> {
    return this.http.get<Language[]>(`${environment.apiBaseUrl}/languages`);
  }
}
```

### Проверка

```bash
cd frontend
npx tsc --noEmit
```

Ошибок быть не должно. Проверьте сужение типов в `AsyncState` — этот код должен компилироваться:

```typescript
function render(state: AsyncState<string[]>): string {
  switch (state.status) {
    case 'idle':
    case 'loading':
      return 'loading';
    case 'success':
      return state.data.join(', ');
    case 'error':
      return state.error.message;
  }
}
```

Если внутри `case 'success'` доступно `state.data` без приведения типов, а внутри `case 'loading'` —
нет, union настроен правильно.

### Коммит

`feat(frontend): add api error normalization and async state model`

---

## Шаг 22. Экран onboarding

### Цель

Пользователь выбирает изучаемый язык, родной язык и уровень CEFR; данные сохраняются на backend.

### Файлы

`frontend/src/app/features/onboarding/{onboarding-page.ts,onboarding-page.html,onboarding-page.scss}`,
`frontend/src/app/features/onboarding/cefr-levels.ts`, правка `app.routes.ts`.

### Действия

Создайте `frontend/src/app/features/onboarding/cefr-levels.ts`:

```typescript
import { CefrLevel } from '../../core/auth/models/user-profile';

export interface CefrLevelOption {
  readonly level: CefrLevel;
  readonly title: string;
  readonly description: string;
}

export const CEFR_LEVEL_OPTIONS: readonly CefrLevelOption[] = [
  { level: 'A1', title: 'A1', description: 'Beginner — знаю отдельные слова и фразы' },
  { level: 'A2', title: 'A2', description: 'Elementary — понимаю простые тексты' },
  { level: 'B1', title: 'B1', description: 'Intermediate — говорю на бытовые темы' },
  { level: 'B2', title: 'B2', description: 'Upper-Intermediate — читаю статьи и сериалы' },
  { level: 'C1', title: 'C1', description: 'Advanced — свободно читаю и обсуждаю' },
  { level: 'C2', title: 'C2', description: 'Proficiency — уровень близкий к носителю' },
];
```

Справочник — константа в модуле, а не в компоненте: он понадобится ещё на экране профиля, и
дублировать список в двух местах нельзя.

Создайте `frontend/src/app/features/onboarding/onboarding-page.ts`:

```typescript
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '../../core/api/api-error';
import { AuthApi } from '../../core/auth/auth-api';
import { AuthSessionStore } from '../../core/auth/auth-session-store';
import { CefrLevel } from '../../core/auth/models/user-profile';
import { TelegramWebAppBridge } from '../../core/telegram/telegram-web-app-bridge';
import { CEFR_LEVEL_OPTIONS } from './cefr-levels';
import { Language, LanguagesApi } from './languages-api';

@Component({
  selector: 'app-onboarding-page',
  imports: [ReactiveFormsModule],
  templateUrl: './onboarding-page.html',
  styleUrl: './onboarding-page.scss',
})
export class OnboardingPage implements OnInit {
  private readonly formBuilder = inject(FormBuilder);
  private readonly languagesApi = inject(LanguagesApi);
  private readonly authApi = inject(AuthApi);
  private readonly session = inject(AuthSessionStore);
  private readonly telegram = inject(TelegramWebAppBridge);
  private readonly router = inject(Router);

  protected readonly levelOptions = CEFR_LEVEL_OPTIONS;
  protected readonly languages = signal<readonly Language[]>([]);
  protected readonly submitting = signal(false);
  protected readonly loadFailed = signal(false);
  protected readonly submitError = signal<ApiError | null>(null);

  protected readonly form = this.formBuilder.nonNullable.group({
    learningLanguageId: [0, [Validators.required, Validators.min(1)]],
    nativeLanguageId: [0, [Validators.required, Validators.min(1)]],
    cefrLevel: ['' as CefrLevel | '', [Validators.required]],
  });

  async ngOnInit(): Promise<void> {
    try {
      const languages = await firstValueFrom(this.languagesApi.listLanguages());
      this.languages.set(languages);
      this.applyDefaultLanguages(languages);
    } catch {
      this.loadFailed.set(true);
    }
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    const { learningLanguageId, nativeLanguageId, cefrLevel } = this.form.getRawValue();
    if (!cefrLevel) {
      return;
    }

    this.submitting.set(true);
    this.submitError.set(null);

    try {
      const updatedUser = await firstValueFrom(
        this.authApi.completeOnboarding({
          learning_language_id: learningLanguageId,
          native_language_id: nativeLanguageId,
          cefr_level: cefrLevel,
        }),
      );
      this.session.applyUpdatedUser(updatedUser);
      this.telegram.notifyHapticSuccess();
      await this.router.navigate(['/']);
    } catch (error) {
      this.submitError.set(toApiError(error));
      this.telegram.notifyHapticError();
    } finally {
      this.submitting.set(false);
    }
  }

  private applyDefaultLanguages(languages: readonly Language[]): void {
    const english = languages.find((language) => language.code === 'en');
    const russian = languages.find((language) => language.code === 'ru');

    this.form.patchValue({
      learningLanguageId: english?.id ?? 0,
      nativeLanguageId: russian?.id ?? 0,
    });
  }
}
```

Продуктовый план требует, чтобы архитектура не была жёстко привязана к паре «русский → английский».
Здесь это выполнено правильно: пара выбирается из справочника, но подставляется по умолчанию.
Пользователь MVP не делает лишних действий, а добавление новой пары не потребует правок кода.

Создайте `frontend/src/app/features/onboarding/onboarding-page.html`:

```html
<section class="onboarding">
  <header class="onboarding__header">
    <h1 class="onboarding__title">Настроим приложение</h1>
    <p class="onboarding__subtitle">Это займёт меньше минуты</p>
  </header>

  @if (loadFailed()) {
    <p class="onboarding__error">Не удалось загрузить языки. Закройте и откройте приложение снова.</p>
  } @else {
    <form class="onboarding__form" [formGroup]="form" (ngSubmit)="submit()">
      <div class="field">
        <label class="field__label" for="learning">Я изучаю</label>
        <select id="learning" class="field__control" formControlName="learningLanguageId">
          @for (language of languages(); track language.id) {
            <option [value]="language.id">{{ language.name }}</option>
          }
        </select>
      </div>

      <div class="field">
        <label class="field__label" for="native">Мой язык</label>
        <select id="native" class="field__control" formControlName="nativeLanguageId">
          @for (language of languages(); track language.id) {
            <option [value]="language.id">{{ language.name }}</option>
          }
        </select>
      </div>

      <fieldset class="levels">
        <legend class="levels__legend">Мой уровень</legend>

        @for (option of levelOptions; track option.level) {
          <label class="level-option">
            <input type="radio" class="level-option__input" formControlName="cefrLevel"
                   [value]="option.level" />
            <span class="level-option__title">{{ option.title }}</span>
            <span class="level-option__description">{{ option.description }}</span>
          </label>
        }
      </fieldset>

      @if (submitError()) {
        <p class="onboarding__error">{{ submitError()?.message }}</p>
      }

      <button class="onboarding__submit" type="submit" [disabled]="form.invalid || submitting()">
        {{ submitting() ? 'Сохраняем…' : 'Продолжить' }}
      </button>
    </form>
  }
</section>
```

Создайте `frontend/src/app/features/onboarding/onboarding-page.scss`:

```scss
.onboarding {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  max-width: 480px;
  margin: 0 auto;

  &__title {
    margin: 0 0 var(--space-2);
    font-size: 22px;
  }

  &__subtitle {
    margin: 0;
    color: var(--color-muted);
  }

  &__form {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  &__error {
    margin: 0;
    color: var(--color-danger);
  }

  &__submit {
    padding: var(--space-3) var(--space-4);
    border: none;
    border-radius: var(--radius-control);
    background: var(--color-accent);
    color: var(--color-accent-text);
    font-size: 16px;
    cursor: pointer;

    &:disabled {
      opacity: 0.5;
      cursor: default;
    }
  }
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);

  &__label {
    color: var(--color-muted);
    font-size: 14px;
  }

  &__control {
    padding: var(--space-3);
    border: 1px solid var(--color-surface);
    border-radius: var(--radius-control);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 16px;
  }
}

.levels {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: none;

  &__legend {
    padding: 0 0 var(--space-2);
    color: var(--color-muted);
    font-size: 14px;
  }
}

.level-option {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-areas:
    'input title'
    'input description';
  gap: 0 var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  cursor: pointer;

  &__input {
    grid-area: input;
    align-self: center;
  }

  &__title {
    grid-area: title;
    font-weight: 600;
  }

  &__description {
    grid-area: description;
    color: var(--color-muted);
    font-size: 13px;
  }
}
```

Размер шрифта в полях ввода — 16px не случайно: при меньшем значении iOS автоматически масштабирует
страницу при фокусе на поле, и вид Mini App «прыгает».

Обновите `frontend/src/app/app.routes.ts`:

```typescript
import { Routes } from '@angular/router';

import { onboardingGuard } from './core/auth/onboarding-guard';

export const routes: Routes = [
  {
    path: 'onboarding',
    loadComponent: () =>
      import('./features/onboarding/onboarding-page').then((m) => m.OnboardingPage),
  },
  {
    path: '',
    canActivate: [onboardingGuard],
    loadComponent: () =>
      import('./features/collections/collections-page').then((m) => m.CollectionsPage),
  },
  { path: '**', redirectTo: '' },
];
```

Создайте временную заглушку главного экрана, чтобы маршрут работал — полностью его сделаем на шаге 40.
`frontend/src/app/features/collections/collections-page.ts`:

```typescript
import { Component } from '@angular/core';

@Component({
  selector: 'app-collections-page',
  template: '<p>Главный экран появится на шаге 40.</p>',
})
export class CollectionsPage {}
```

Это единственное место, где допустим инлайновый `template` — временная заглушка на один шаг. В шаге 40
она заменяется полноценным компонентом с отдельными файлами.

### Проверка

Полная проверка — внутри Telegram на шаге 23. Сейчас проверьте сборку и вид экрана.

Чтобы увидеть экран в браузере, временно откройте его напрямую: в `app.ts` в `ngOnInit` закомментируйте
проверку статуса и в `app.html` временно замените `@switch` на `<router-outlet />`, затем откройте
`http://localhost:4200/onboarding`. После проверки верните код обратно.

```bash
cd frontend
npx tsc --noEmit
npm run build
```

Проверьте глазами: уровни выбираются, кнопка «Продолжить» неактивна до выбора уровня, поля языков
заполнены значениями English и Русский.

### Коммит

`feat(frontend): add onboarding screen with language and level selection`

---

## Шаг 23. Nginx, Dockerfile frontend, публичный HTTPS-туннель

### Цель

Всё приложение доступно по одному адресу через Nginx, а Mini App реально открывается из Telegram и
проходит аутентификацию.

### Почему нужен туннель

Telegram открывает Mini App только по HTTPS с публично доступного домена. `http://localhost:4200`
не подойдёт. До появления VPS (шаг 67) используем туннель, который выдаёт временный публичный
HTTPS-адрес на ваш локальный порт.

### Файлы

`frontend/Dockerfile`, `infra/nginx/nginx.conf`, правка `docker-compose.yml`.

### Действия

Создайте `frontend/Dockerfile`:

```dockerfile
FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build -- --configuration=production

FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

RUN printf 'server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
  location / {\n\
    try_files $uri $uri/ /index.html;\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
```

Многоступенчатая сборка: Node нужен только для компиляции, в итоговый образ попадают статические
файлы и Nginx — это десятки мегабайт вместо гигабайта. Директива `try_files ... /index.html`
обязательна для SPA: без неё прямое обращение к `/onboarding` даст 404, потому что такого файла нет,
а маршрутизацию выполняет Angular.

Проверьте фактический путь сборки — он зависит от имени проекта в `angular.json`:

```bash
cd frontend && npm run build && ls dist/
```

Если папка называется иначе, поправьте путь в `COPY --from=build`.

Создайте `infra/nginx/nginx.conf` — внешний обратный прокси:

```nginx
worker_processes auto;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    sendfile on;
    keepalive_timeout 65;
    client_max_body_size 1m;

    log_format json_combined escape=json
        '{"time":"$time_iso8601","remote_addr":"$remote_addr","method":"$request_method",'
        '"path":"$uri","status":$status,"bytes":$body_bytes_sent,'
        '"duration":$request_time,"correlation_id":"$http_x_correlation_id"}';

    access_log /var/log/nginx/access.log json_combined;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    upstream backend_upstream {
        server backend:8000;
    }

    upstream frontend_upstream {
        server frontend:80;
    }

    server {
        listen 80;
        server_name _;

        location /api/ {
            proxy_pass http://backend_upstream;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 60s;
        }

        location = /health {
            proxy_pass http://backend_upstream/health;
        }

        location = /ready {
            proxy_pass http://backend_upstream/ready;
        }

        location /media/ {
            alias /srv/media/;
            expires 30d;
            add_header Cache-Control "public, immutable";
            access_log off;
        }

        location / {
            proxy_pass http://frontend_upstream;
            proxy_set_header Host $host;
        }
    }
}
```

`client_max_body_size 1m` ограничивает размер запроса на входе — наши запросы измеряются килобайтами,
и это дешёвая защита. Раздача `/media/` напрямую из Nginx означает, что аудиофайлы не проходят через
Python: отдача статики — не работа приложения.

Логи в JSON с `correlation_id` дают возможность сопоставить запись Nginx с записью backend — той же
командой `grep` по одному идентификатору.

Добавьте сервисы в `infra/docker-compose.yml`:

```yaml
  frontend:
    build:
      context: ../frontend
    restart: unless-stopped
    depends_on:
      - backend

  nginx:
    image: nginx:1.27-alpine
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - media-data:/srv/media:ro
    depends_on:
      - backend
      - frontend
```

Теперь всё приложение — на `http://localhost:8080`.

Поднимите и проверьте:

```bash
cd infra
docker compose up -d --build
curl -s http://localhost:8080/health
curl -s http://localhost:8080/api/v1/languages | python3 -m json.tool
curl -sI http://localhost:8080/ | head -3
```

### Публикация через туннель

Вариант с `cloudflared` — бесплатно и без регистрации:

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8080
```

В выводе появится адрес вида `https://random-words-1234.trycloudflare.com`. Скопируйте его.

Альтернатива — `ngrok` (требует бесплатную регистрацию, зато даёт стабильный адрес на время сессии):

```bash
brew install ngrok
ngrok http 8080
```

Пропишите адрес в `.env`:

```bash
MINI_APP_URL=https://random-words-1234.trycloudflare.com
```

Перезапустите бота и backend, чтобы подхватили переменную:

```bash
docker compose restart telegram-bot backend
```

Зарегистрируйте Mini App в BotFather:

1. откройте [@BotFather](https://t.me/BotFather), отправьте `/mybots`;
2. выберите бота → `Bot Settings` → `Menu Button` → `Configure menu button`;
3. вставьте адрес туннеля;
4. задайте текст кнопки, например `Открыть словарь`.

Адрес туннеля меняется при каждом перезапуске `cloudflared`. Это нормально: на время недели 1
обновляйте `.env` и настройку BotFather. Постоянный адрес появится на шаге 67.

### Проверка — главная за неделю

Откройте Mini App из Telegram: `/start` → кнопка «Открыть приложение».

Должно произойти следующее:

1. приложение открывается внутри Telegram, без белого экрана;
2. показывается экран onboarding;
3. выбор языков и уровня работает;
4. после «Продолжить» появляется заглушка главного экрана.

Проверьте логи — в них виден весь путь запроса:

```bash
docker compose logs --tail=50 backend
```

Найдите запись про `POST /api/v1/auth/telegram` со статусом 200 и запись
`telegram authentication succeeded`.

Проверьте данные в БД:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "
select u.id, u.cefr_level, u.onboarding_completed_at, l1.code as learning, l2.code as native
from users u
left join languages l1 on l1.id = u.learning_language_id
left join languages l2 on l2.id = u.native_language_id;
"
```

Должна быть строка с вашим уровнем, кодами `en`/`ru` и непустым `onboarding_completed_at`.

Закройте Mini App и откройте снова — onboarding больше не показывается, вы попадаете сразу на главный
экран. Это проверяет, что токен сохранился в `localStorage` и восстановление сессии работает.

Если что-то не работает — смотрите [11-troubleshooting.md](11-troubleshooting.md), раздел про Telegram
Mini App.

### Коммит

`feat(infra): add nginx reverse proxy and frontend container`

---

## Шаг 24. CI на GitHub Actions и проверка результатов недели

### Цель

При каждом push и pull request автоматически проверяются линтеры, типы, тесты и сборка образов.

### Файлы

`.github/workflows/ci.yml`.

### Действия

Создайте репозиторий на GitHub и свяжите:

```bash
gh repo create english-vocabulary-app --private --source=. --remote=origin
git push -u origin main
```

Если `gh` не установлен: `brew install gh && gh auth login`.

Создайте `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend

    services:
      postgres:
        image: postgres:17-alpine
        env:
          POSTGRES_DB: vocabulary_test
          POSTGRES_USER: vocabulary
          POSTGRES_PASSWORD: test-password
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

      redis:
        image: redis:8-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10

    env:
      SECRET_KEY: ci-secret-key-not-used-in-production
      POSTGRES_HOST: localhost
      POSTGRES_DB: vocabulary_test
      POSTGRES_USER: vocabulary
      POSTGRES_PASSWORD: test-password
      REDIS_URL: redis://localhost:6379/0
      CELERY_BROKER_URL: redis://localhost:6379/1
      CELERY_RESULT_BACKEND: redis://localhost:6379/2

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - run: uv sync --frozen

      - name: Lint
        run: uv run ruff check app tests

      - name: Format check
        run: uv run ruff format --check app tests

      - name: Type check
        run: uv run mypy app

      - name: Migrations apply cleanly
        run: uv run alembic upgrade head

      - name: Tests
        run: uv run pytest -v

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - run: npm ci

      - name: Type check
        run: npx tsc --noEmit

      - name: Tests
        run: npm test -- --watch=false

      - name: Build
        run: npm run build -- --configuration=production

  docker:
    runs-on: ubuntu-latest
    needs: [backend, frontend]

    steps:
      - uses: actions/checkout@v4

      - name: Build backend image
        run: docker build -t vocabulary-backend:ci ./backend

      - name: Build frontend image
        run: docker build -t vocabulary-frontend:ci ./frontend

      - name: Build bot image
        run: docker build -t vocabulary-bot:ci ./bot
```

Три момента, которые стоит понимать. Шаг `Migrations apply cleanly` ловит самую неприятную категорию
ошибок — миграцию, которая работает на вашей базе (потому что там уже есть нужное состояние), но
падает на чистой. Проверка `ruff format --check` не меняет файлы, а падает при расхождении —
форматирование должно быть сделано локально. Сборка образов вынесена в отдельную задачу после тестов,
чтобы не тратить минуты CI, когда тесты уже красные.

`concurrency` с `cancel-in-progress` отменяет предыдущий запуск при новом push в ту же ветку.

Настройте защиту ветки `main` в настройках репозитория: Settings → Branches → Add rule → требовать
прохождение проверок перед merge. Продуктовый план предусматривает работу через feature-ветки и PR,
и это то, что делает правило реальным.

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add backend, frontend and docker build pipelines"
git push
```

### Проверка

```bash
gh run list --limit 3
gh run watch
```

Все три задачи должны быть зелёными. Если backend падает на `alembic upgrade head` — скорее всего
`env.py` не видит переменные окружения; проверьте, что `Settings` читает их из окружения, а не
только из файла `.env` (файла на CI нет, и это нормально).

Проверьте работу на pull request:

```bash
git checkout -b chore/verify-ci
git commit --allow-empty -m "chore: verify ci on pull request"
git push -u origin chore/verify-ci
gh pr create --fill
gh pr checks
```

После проверки можно удалить ветку.

### Коммит

`ci: add backend, frontend and docker build pipelines`

---

## Definition of Done недели 1

Проверьте каждый пункт вживую, а не по памяти:

- [ ] `/start` в Telegram присылает кнопку, которая открывает Mini App
- [ ] Mini App проходит аутентификацию: `POST /api/v1/auth/telegram` возвращает 200
- [ ] Пользователь появился в таблице `users`, идентичность — в `auth_identities`
- [ ] Onboarding сохраняется: заполнены языки, уровень и `onboarding_completed_at`
- [ ] Повторное открытие приложения не показывает onboarding
- [ ] `docker compose up` поднимает postgres, redis, backend, celery-worker, telegram-bot, frontend, nginx
- [ ] `curl http://localhost:8080/ready` возвращает 200 со всеми `true`
- [ ] Остановка Redis переводит `/ready` в 503 — проверка настоящая
- [ ] Celery-задача выполняется, worker видит её в логах
- [ ] Логи в JSON, в каждой записи есть `correlation_id`
- [ ] Подделанный `initData` отклоняется — тесты проходят
- [ ] CI зелёный на `main` и на pull request
- [ ] `.env` не отслеживается git

### Что делать, если неделя затянулась

Если к концу недели не работает только публикация через туннель, а всё остальное готово — двигайтесь
дальше на неделю 2 и вернитесь к шагу 23 позже: для разработки словаря Telegram не нужен, API
тестируется через `curl`.

Если не работает аутентификация — останавливайтесь и доводите. Всё остальное в приложении зависит от
`CurrentUser`, и обходить это временными заглушками означает переписывать позже.

Дальше: [04-week2-vocabulary.md](04-week2-vocabulary.md), шаг 25.
