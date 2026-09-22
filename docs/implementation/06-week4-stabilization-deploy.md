# Неделя 4 — Stabilization + Deploy (шаги 58–72)

## Цель недели

MVP пригоден для ежедневного использования: события пишутся, аккаунт удаляется без порчи общего лексикона, лимиты и ошибки предсказуемы, критические сценарии покрыты тестами, production Mini App работает по HTTPS, бэкап снимается и хотя бы раз восстанавливался.

Ориентировочное время: 25 часов.

К этому моменту уже есть:

* недели 1–3: auth, onboarding, словарь, enrichment, занятия, неправильные глаголы;
* `/health`, `/ready`, JSON-логи и `X-Correlation-ID` — шаг 8 и шаг 10;
* `--concurrency=2` у Celery — шаг 17;
* длина `init_data` и других полей в Pydantic — шаги 16 и 35–47;
* CI с pytest и Vitest — шаг 24.

Неделя 4 не добавляет учебный функционал. Не реализуются изображения, Sentry, Grafana, TTS, SRS — они уходят в `docs/post-mvp.md` на шаге 72.

Каталог тестов и образцы фикстур — в [10-testing-reference.md](10-testing-reference.md). Этот файл говорит, **когда** их писать и как встроить в приложение. Справочник — **что** именно проверять.

---

## Шаг 58. Продуктовые события

### Цель

Шесть событий из продуктового плана пишутся в таблицу `product_events` в той же транзакции, что и действие пользователя. Роутеры событий не вызывают.

События:

* `onboarding_completed`
* `collection_created`
* `word_added`
* `study_started`
* `study_stage_completed`
* `study_completed`

`opened_app` из раздела метрик в таблицу не пишется: это клиентский факт открытия Mini App, а не доменное действие. Добавлять его сейчас не нужно.

### Файлы

```text
backend/app/analytics/__init__.py
backend/app/analytics/models.py
backend/app/analytics/repository.py
backend/app/analytics/service.py
backend/alembic/versions/<rev>_add_product_events.py
backend/app/common/models_registry.py
backend/app/users/service.py
backend/app/collections/service.py
backend/app/vocabulary/service.py
backend/app/study/service.py
backend/tests/test_product_events.py
```

Роутера и схем API нет: события не читаются клиентом в MVP.

### Действия

Модель — ровно поля из плана:

```python
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import Base


class ProductEventName(StrEnum):
    ONBOARDING_COMPLETED = "onboarding_completed"
    COLLECTION_CREATED = "collection_created"
    WORD_ADDED = "word_added"
    STUDY_STARTED = "study_started"
    STUDY_STAGE_COMPLETED = "study_stage_completed"
    STUDY_COMPLETED = "study_completed"


class ProductEvent(Base):
    __tablename__ = "product_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

`ondelete="CASCADE"` нужен шагу 59: персональная аналитика удаляется вместе с пользователем, общий лексикон — нет.

Индекс по `event_name` — чтобы потом считать activation rate SQL-запросом, а не полным сканом.

Репозиторий только вставляет (`session.add(ProductEvent(...))`), без решений «надо ли писать». Сервис `ProductEventService.record(user_id, event_name, payload)` — единственная точка записи. Payload без `source_context`, `personal_note`, токенов и Telegram identity.

Вызовы — из существующих сервисов, **до** `commit()`. Иначе событие и действие разъедутся.

`UserProfileService.complete_onboarding` — событие только при первом прохождении (`onboarding_completed_at is None` до записи, та же идемпотентность шага 16):

```python
if is_first_completion:
    await ProductEventService(self._session).record(
        user_id=user.id,
        event_name=ProductEventName.ONBOARDING_COMPLETED,
        payload={
            "cefr_level": update.cefr_level.value,
            "native_language_id": update.native_language_id,
            "learning_language_id": update.learning_language_id,
        },
    )
```

`CollectionService.create` — после добавления коллекции, до commit:

```python
await ProductEventService(self._session).record(
    user_id=user.id,
    event_name=ProductEventName.COLLECTION_CREATED,
    payload={"collection_id": str(collection.id), "name": collection.name},
)
```

После `flush()` у коллекции уже есть `id`. Системную тему неправильных глаголов (`is_system=True`, `user_id is None`) не пишите: это не действие пользователя.

`VocabularyService.create_item` — `word_added` и для word, и для phrase. В payload: `vocabulary_item_id`, `lexeme_id`, `meaning_id`, `lexeme_type`. Не кладите исходный текст фразы целиком, если он длинный и совпадает с `source_context`.

`StudySessionService.create` — `study_started` с `session_id`, `collection_id`, `item_count`, `selection_mode` (`random` / `manual` / `new_first`).

`StudySessionService.save_progress` — `study_stage_completed` только когда `current_stage` реально сменился, не на каждое сохранение попытки.

`StudySessionService.complete` — `study_completed` с `session_id` и `item_count`. Баллов в MVP нет.

Зарегистрируйте модель в `models_registry.py` и сгенерируйте миграцию:

```bash
cd backend
POSTGRES_HOST=localhost uv run alembic revision --autogenerate -m "add product events"
POSTGRES_HOST=localhost uv run alembic upgrade head
```

В миграции проверьте: таблица `product_events`, FK на `users.id` с `ondelete='CASCADE'`, индексы по `user_id` и `event_name`.

Тест `backend/tests/test_product_events.py` — через сервис, не через роутер. Первый onboarding пишет одну строку, повторный PATCH — ноль новых. Создание коллекции пишет `collection_created`. Полный каталог — [10-testing-reference.md](10-testing-reference.md), раздел про события.

### Проверка

```bash
cd backend
POSTGRES_HOST=localhost uv run pytest tests/test_product_events.py -v
```

После живого onboarding и создания темы:

```bash
cd infra
docker compose exec postgres psql -U vocabulary -d vocabulary -c "
select event_name, payload, created_at
from product_events
order by id;
"
```

Должны быть `onboarding_completed` и `collection_created`. Повторный вход без новых действий строки не добавляет.

### Коммит

`feat(analytics): record product events from domain services`

---

## Шаг 59. Удаление аккаунта

### Цель

`DELETE /api/v1/users/me` удаляет только персональные данные. `Lexeme`, `Meaning`, `Translation`, `MeaningContent`, системные irregular verbs и общие audio references остаются.

Персональное по плану: `User`, `AuthIdentity`, `UserVocabularyItem` (включая `personal_note` / `source_context`), пользовательские `Collection` / `CollectionItem`, `StudySession` / `StudySessionItem`, `ProductEvent`.

### Файлы

```text
backend/app/users/service.py
backend/app/users/router.py
frontend/src/app/core/auth/auth-api.ts
frontend/src/app/features/profile/profile-page.ts
frontend/src/app/features/profile/profile-page.html
frontend/src/app/features/profile/profile-page.scss
backend/tests/test_delete_account.py
```

Новой миграции нет, если FK уже такие:

| Таблица | Колонка | `ondelete` |
| --- | --- | --- |
| `auth_identities.user_id` | CASCADE | шаг 12 |
| `product_events.user_id` | CASCADE | шаг 58 |
| `user_vocabulary_items.user_id` | CASCADE | неделя 2 |
| `user_vocabulary_items.meaning_id` | RESTRICT | неделя 2 |
| `collections.user_id` | CASCADE, nullable | неделя 2 |
| `collection_items.collection_id` | CASCADE | неделя 2 |
| `collection_items.user_vocabulary_item_id` | CASCADE | неделя 2 |
| `study_sessions.user_id` | CASCADE | неделя 3 |
| `study_session_items.session_id` | CASCADE | неделя 3 |

Системная тема неправильных глаголов: `user_id IS NULL`, `is_system = true` — строка не трогается.

Если какой-то FK на пользователя стоит `RESTRICT` или указывает на `Meaning` с `CASCADE` — исправьте новой миграцией. Старую не редактируйте.

### Действия

Сервис удаляет пользователя. Каскад БД зачищает персональные таблицы. Коммит один.

```python
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import EntityNotFoundError
from app.users.models import User


class UserAccountService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_account(self, user_id: UUID) -> None:
        user = await self._session.get(User, user_id)
        if user is None:
            raise EntityNotFoundError("user not found")

        await self._session.delete(user)
        await self._session.commit()
```

Не обходите ORM сырым `DELETE FROM users` в обход сессии: связанные объекты в identity map останутся «живыми». Не удаляйте `Lexeme` «на всякий случай» — даже если это слово добавил только этот пользователь.

Роутер тонкий:

```python
from fastapi import Response, status

from app.auth.dependencies import CurrentUser, DbSession
from app.users.service import UserAccountService


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user_account(
    user: CurrentUser,
    session: DbSession,
) -> Response:
    await UserAccountService(session).delete_account(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

После этого JWT ещё формально валиден до истечения TTL, но `get_current_user` не найдёт строку в `users` и вернёт 401. Этого достаточно: отдельный denylist токенов в MVP не вводим.

На фронте — экран профиля (заглушка с недели 1 / навигация). Кнопка «Удалить аккаунт», подтверждение вторым нажатием или отдельным диалогом. После 204:

* очистить `localStorage` с токеном;
* вызвать `Telegram.WebApp.close()` если мост доступен;
* иначе показать «аккаунт удалён, закройте Mini App».

В `auth-api.ts`:

```typescript
deleteAccount(): Observable<void> {
  return this.http.delete<void>(`${environment.apiBaseUrl}/users/me`);
}
```

Компонент не собирает URL сам.

Тест `test_delete_account.py`:

1. Пользователь A добавляет слово `bank` → появляются `Lexeme` / `Meaning` / `Translation` / `MeaningContent`.
2. `DELETE /users/me` → 204.
3. Нет строк в `users`, `auth_identities`, `user_vocabulary_items`, `collections` этого пользователя, `study_sessions`, `product_events`.
4. Строки лексикона на месте.
5. Повторный `GET /users/me` с тем же JWT → 401.
6. Пользователь B с тем же `meaning_id` в словаре не затрагивается — заведите второго пользователя в том же тесте.

Фикстуры и фабрики — из [10-testing-reference.md](10-testing-reference.md).

### Проверка

```bash
cd backend
POSTGRES_HOST=localhost uv run pytest tests/test_delete_account.py -v
```

Живая проверка: добавьте слово, откройте карточку, удалите аккаунт, зайдите снова через Telegram. Появится новый `users.id`, onboarding с нуля. Слово в `lexemes` останется:

```sql
select count(*) from lexemes;
select count(*) from users;
```

Первое число не уменьшилось, второе — новый пользователь.

### Коммит

`feat(users): delete account and keep shared lexicon`

---

## Шаг 60. Лимиты: частота запросов, длина ввода, суточный лимит AI

### Цель

Три независимых ограничения из раздела 29 плана:

1. частота HTTP — Redis-счётчики, зависимость FastAPI;
2. длина ввода — уже в Pydantic, на этом шаге **сверить и добить пропуски**;
3. AI — 50 запросов в сутки на пользователя (`ai_daily_request_limit_per_user` из шага 7);
4. Celery — `--concurrency=2` уже есть на шаге 17, продублировать в конфиге приложения, чтобы лимит не жил только в compose.

Свою библиотеку rate limit не ставим: в README зафиксированы Redis-счётчики.

### Файлы

```text
backend/app/common/rate_limit.py
backend/app/common/ai_usage.py
backend/app/common/errors.py
backend/app/common/celery_app.py
backend/app/auth/dependencies.py
backend/app/lexicon/schemas.py
backend/app/vocabulary/schemas.py
backend/app/collections/schemas.py
backend/app/users/schemas.py
backend/app/lexicon/lookup_service.py
backend/app/enrichment/service.py
backend/tests/test_rate_limit.py
backend/tests/test_ai_daily_limit.py
```

### Действия

`RateLimitExceededError` уже объявлен на шаге 15 — не дублируйте. Добавьте:

```python
class AiDailyLimitExceededError(ApplicationError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("ai daily limit exceeded")
```

Счётчик в Redis: `INCR` + `EXPIRE` на первом попадании. Атомарность — через Lua или `SET NX` для expire. Простой безопасный вариант:

```python
from redis.asyncio import Redis

from app.common.errors import RateLimitExceededError

WINDOW_SECONDS = 60


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, *, key: str, limit: int, window_seconds: int = WINDOW_SECONDS) -> None:
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, window_seconds)
        if count > limit:
            ttl = await self._redis.ttl(key)
            raise RateLimitExceededError(retry_after_seconds=max(ttl, 1))
```

Ключи:

| Действие | Ключ | Лимит |
| --- | --- | --- |
| все аутентифицированные запросы | `rl:user:{user_id}:all` | 120 / мин |
| `POST /lexemes/lookup` | `rl:user:{user_id}:lookup` | 30 / мин |
| `POST /vocabulary` | `rl:user:{user_id}:vocabulary_write` | 20 / мин |
| `POST /study-sessions` | `rl:user:{user_id}:study_start` | 10 / мин |
| `POST /auth/telegram` | `rl:ip:{client_ip}:auth` | 10 / мин |

Зависимость для защищённых роутеров:

```python
from typing import Annotated

from fastapi import Depends, Request

from app.auth.dependencies import CurrentUser
from app.common.rate_limit import RedisRateLimiter
from app.common.redis_client import get_redis_client


async def enforce_user_rate_limit(request: Request, user: CurrentUser) -> None:
    limiter = RedisRateLimiter(get_redis_client())
    await limiter.hit(key=f"rl:user:{user.id}:all", limit=120)

    route_limits: dict[str, tuple[str, int]] = {
        "/api/v1/lexemes/lookup": ("lookup", 30),
        "/api/v1/vocabulary": ("vocabulary_write", 20),
        "/api/v1/study-sessions": ("study_start", 10),
    }
    match = route_limits.get(request.url.path)
    if match is not None and request.method == "POST":
        suffix, limit = match
        await limiter.hit(key=f"rl:user:{user.id}:{suffix}", limit=limit)


RequireUserRateLimit = Annotated[None, Depends(enforce_user_rate_limit)]
```

Подключите `RequireUserRateLimit` на роутерах словаря, lookup, коллекций и занятий. На `GET /languages` и `/health` не вешайте.

Для `POST /auth/telegram` — отдельная зависимость по IP (`request.client.host`). За Nginx в production смотрите `X-Forwarded-For` только если Nginx его выставляет сам и `real_ip` настроен; иначе клиент подделает заголовок.

Суточный лимит AI — другой ключ и другая ошибка. Счётчик увеличивается **только после успешного вызова провайдера**, проверка — **до** вызова. Иначе сетевой сбой съест квоту, а исчерпанная квота не должна идти в OpenAI.

```python
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from app.common.errors import AiDailyLimitExceededError
from app.common.settings import get_settings


class AiDailyUsageLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, user_id: UUID) -> str:
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        return f"ai:daily:{user_id}:{day}"

    async def ensure_available(self, user_id: UUID) -> None:
        limit = get_settings().ai_daily_request_limit_per_user
        current = int(await self._redis.get(self._key(user_id)) or 0)
        if current >= limit:
            raise AiDailyLimitExceededError(retry_after_seconds=_seconds_until_utc_midnight())

    async def increment(self, user_id: UUID) -> None:
        key = self._key(user_id)
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, _seconds_until_utc_midnight())
```

Вызов в `LexemeLookupService` перед `AIProvider` (fallback значения или definition/example, если lookup сам ходит в AI) и в `EnrichmentService` перед генерацией `MeaningContent`. Enrichment идёт из Celery: `user_id` берите с `UserVocabularyItem`, не из HTTP.

Если лимит исчерпан на enrichment — карточка остаётся `PARTIAL` / `FAILED` по правилам недели 2, а не вечный `ENRICHING`. Пользователь видит перевод из словаря.

Длина ввода — сверка, не новая библиотека:

| Поле | Лимит | Где |
| --- | --- | --- |
| `init_data` | 1–4096 | `TelegramAuthRequest`, шаг 16 |
| слово / фраза | 1–80 | lookup и create vocabulary |
| phrase | не больше 5 слов после нормализации | сервис lookup / create, не только Pydantic |
| `source_context` | 0–500 | lookup и create |
| `personal_note` | 0–500 | PATCH vocabulary |
| имя темы | 1–80 | create/update collection |
| описание темы | 0–500 | create/update collection |

Прогоните схемы: каждое строковое поле с `Field(max_length=...)`. Лимит фразы в 5 слов — доменная проверка в сервисе (`ValidationFailedError`), потому что «слово» считается после нормализации.

Celery: в `celery_app.conf.update` добавьте `worker_concurrency=2`. В `docker-compose.yml` флаг `--concurrency=2` оставьте. Два места с одним числом лучше, чем забытый флаг на production-compose.

Тесты: 121-й запрос за минуту с одного пользователя даёт 429 и `Retry-After`. Два пользователя не делят счётчик. 51-й вызов AI за сутки — `AiDailyLimitExceededError`, `FakeAIProvider` не вызывается. Провайдеры мокаются, Redis — тот же, что в CI (шаг 24).

### Проверка

```bash
cd backend
POSTGRES_HOST=localhost REDIS_URL=redis://localhost:6379/0 uv run pytest \
  tests/test_rate_limit.py tests/test_ai_daily_limit.py -v
```

Вручную:

```bash
TOKEN=...
for i in $(seq 1 35); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"text":"bank"}' \
    http://localhost:8080/api/v1/lexemes/lookup
done
```

После 30-го lookup — `429`. В заголовке `Retry-After` есть число секунд.

```bash
cd infra
docker compose exec celery-worker celery -A app.common.celery_app:celery_app inspect stats
```

В stats `pool.max-concurrency` равен 2.

### Коммит

`feat(backend): add redis rate limits and daily ai quota`

---

## Шаг 61. Единая обработка ошибок

### Цель

Сервисы бросают доменные исключения. Роутеры больше не переводят их в `HTTPException` по одному. Фронт нормализует ответ в `ApiError` и не глотает ошибки.

Контракт тела ошибки один:

```json
{
  "error": {
    "code": "validation",
    "message": "native and learning languages must differ"
  }
}
```

Поле `detail` FastAPI по умолчанию для своих 422 оставляем совместимым: фронт читает и `error.message`, и строковый `detail` (шаг 21 уже смотрит `detail` — расширьте, не ломайте).

### Файлы

```text
backend/app/common/errors.py
backend/app/common/error_handlers.py
backend/app/main.py
backend/app/users/router.py и остальные доменные роутеры (убрать локальный HTTPException)
frontend/src/app/core/api/api-error.ts
frontend/src/app/core/api/api-error.spec.ts
backend/tests/test_error_handlers.py
```

### Действия

Карта домен → HTTP. Новые коды добавляйте сюда, не в роутеры.

```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.auth.tokens import InvalidAccessTokenError
from app.common.errors import (
    AiDailyLimitExceededError,
    ApplicationError,
    EntityNotFoundError,
    PermissionDeniedError,
    RateLimitExceededError,
    ValidationFailedError,
)

ERROR_MAP: tuple[tuple[type[ApplicationError], int, str], ...] = (
    (InvalidAccessTokenError, 401, "unauthorized"),
    (PermissionDeniedError, 403, "forbidden"),
    (EntityNotFoundError, 404, "not_found"),
    (ValidationFailedError, 422, "validation"),
    (RateLimitExceededError, 429, "rate_limited"),
    (AiDailyLimitExceededError, 429, "rate_limited"),
)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def handle_application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        status_code, code = _status_for(exc)
        headers: dict[str, str] = {}
        if isinstance(exc, RateLimitExceededError | AiDailyLimitExceededError):
            headers["Retry-After"] = str(exc.retry_after_seconds)
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": code, "message": str(exc)}},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation", "message": "request validation failed"}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled application error")
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "server", "message": "internal server error"}},
        )
```

В `handle_unexpected` клиенту не отдавайте `str(exc)` — там могут быть строки подключения к БД. В лог — полностью, без секретов из settings.

Вызов `register_error_handlers(app)` в `create_app()`.

Уберите `try/except HTTPException` из роутеров пользователей, коллекций, словаря, занятий, lookup. Роутер вызывает сервис и возвращает схему. Исключение ловит handler.

`POST /auth/telegram` по-прежнему отвечает одной фразой на все `TelegramAuthError` (шаг 16). Это не «проглатывание»: наружу 401, в лог — конкретный подкласс. Handler для `TelegramAuthError` зарегистрируйте отдельно с фиксированным `message`.

Фронт: расширьте `extractServerMessage` шага 21 — сначала `body.error.message`, затем строковый `detail`. `toApiError` без изменений по kind (включая 429).

Компоненты получают `AsyncState` со статусом `error`. Пустых `catch {}` в feature-коде нет. Ошибка poll enrichment — состояние карточки, не молчание.

Тесты handler: `ValidationFailedError` → 422 и тело с `error.code`. Непойманный `RuntimeError` → 500 и сообщение `internal server error`, не текст исключения. Vitest на `toApiError` — 429 читает `Retry-After`, тело `{error:{message}}` побеждает дефолтный текст.

### Проверка

```bash
cd backend
POSTGRES_HOST=localhost uv run pytest tests/test_error_handlers.py -v
cd ../frontend
npx ng test --watch=false --include=src/app/core/api/api-error.spec.ts
```

```bash
curl -s -X PATCH http://localhost:8080/api/v1/users/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"native_language_id":1,"learning_language_id":1,"cefr_level":"A2"}'
```

Ожидается 422 и `{"error":{"code":"validation",...}}`. В UI onboarding — текст с сервера, не белый экран.

### Коммит

`feat: map domain errors to http and normalize api errors`

---

## Шаг 62. Тесты backend

### Цель

Критичные сценарии раздела 31 плана покрыты pytest. Как писать фикстуры, HMAC и идемпотентность enrichment — только в [10-testing-reference.md](10-testing-reference.md). Здесь список файлов и прогон.

CI уже запускает `uv run pytest -v` на шаге 24. Новые тесты подхватываются сами, job не дублируйте.

### Файлы

`backend/tests/conftest.py` плюс файлы из таблицы ниже. Часть уже есть с недель 1–3 — доберите дыры.

### Действия

Закройте каталог [10-testing-reference.md](10-testing-reference.md) §5. Провайдеры — фейки. Сеть до Yandex/OpenAI запрещена.

| Тема плана | Файл | Суть |
| --- | --- | --- |
| normalization | `test_normalization.py` | один `Lexeme` на `(language_id, normalized_text)`, word vs phrase |
| duplicate prevention | `test_duplicate_prevention.py` | unique `user_id + meaning_id`; два пользователя — две карточки |
| typo suggestion | `test_typo_suggestion.py` | `clarfy` → `clarify` через `pg_trgm` |
| random / new-first | `test_study_selection.py` | не брать `PENDING`/`ENRICHING`; NULL `last_studied_at` раньше |
| dictionary fallback | `test_lookup_fallback.py` | пустой primary → fallback; IPA дополняется, переводы не затираются |
| AI fallback | `test_ai_fallback.py` | AI meanings только если словари пусты; `source_context` не в `MeaningContent` |
| enrichment status | `test_enrichment_status.py` | `READY` / `PARTIAL` / не вечный `ENRICHING` |
| retry | `test_enrichment_retry.py` | backoff `2 ** retries * 10`, `max_retries=3` |
| Telegram auth | `test_telegram_auth.py` | HMAC, expiry, подмена user id — шаг 14 |
| идемпотентность | `test_enrichment_idempotency.py` | lock + unique, один вызов AI |

Не тестируйте mapping SQLAlchemy и тексты логов.

### Проверка

```bash
cd backend
POSTGRES_HOST=localhost uv run ruff check app tests
POSTGRES_HOST=localhost uv run mypy app
POSTGRES_HOST=localhost uv run pytest -v
```

Красный тест — дыра в неделях 2–3, чините до деплоя. Не skip-айте критичные кейсы.

### Коммит

`test(backend): cover mvp-critical domain scenarios`

---

## Шаг 63. Тесты frontend

### Цель

Покрыт учебный клиентский контур из плана: состояние занятия, этапы, 3 попытки, пропуск sentence для phrase, matching, restore. Vitest, Karma нет (Angular 22).

### Файлы

```text
frontend/src/app/features/study/study-session-store.spec.ts
frontend/src/app/features/study/matching-pairs.spec.ts
frontend/src/app/features/study/answer-checking.spec.ts
frontend/src/app/core/api/api-error.spec.ts
```

Чистые функции (проверка ответа, сборка пар matching, «нужен ли sentence-этап») тестируйте без TestBed. Store — через TestBed, как в [02-primer-angular.md](02-primer-angular.md) и справочнике.

### Действия

Кейсы — [10-testing-reference.md](10-testing-reference.md) §6, образец TestBed — §10.

| Тема | Инвариант |
| --- | --- |
| этапы word | introduction → matching → sentence → definition → `completeSession` |
| 3 попытки | третья ошибка раскрывает ответ; успех с первой — нет |
| phrase skip | после matching сразу definition, sentence нет |
| matching | клики, не DnD; неверная пара сбрасывает выбор |
| restore | `in_progress` + `current_stage: sentence` не сбрасывает на introduction |

`StudyApi` — `useValue`. HTTP из store не уходит. Вёрстку кнопок не тестируйте.

### Проверка

```bash
cd frontend
npx tsc --noEmit
npx ng test --watch=false
```

Все новые spec-файлы зелёные. CI job `frontend` шага 24 подхватит их сам.

### Коммит

`test(frontend): cover study store stages attempts matching restore`

---

## Шаг 64. Три E2E-сценария

### Цель

Playwright гоняет три сценария раздела 31 плана против собранного приложения (nginx :8080). Настоящий Telegram не нужен: E2E подписывает `initData` тем же HMAC, что unit-тесты шага 14, и кладёт строку в `window.Telegram.WebApp.initData`.

### Файлы

```text
e2e/package.json
e2e/playwright.config.ts
e2e/support/telegram-init-data.ts
e2e/support/auth.ts
e2e/tests/onboarding-add-word.spec.ts
e2e/tests/study-finish.spec.ts
e2e/tests/session-restore.spec.ts
```

Отдельный пакет, чтобы `ng test` остался быстрым. На CI E2E — отдельный job, не блокер сборки образов, но job добавьте: иначе сценарии живут только на ноутбуке.

### Действия

```bash
mkdir -p e2e/tests e2e/support
cd e2e
npm init -y
npm install -D @playwright/test
npx playwright install chromium
```

`playwright.config.ts`: `baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080'`, один worker для стабильности сессии БД, `trace: 'on-first-retry'`.

Подпись `initData` — копия алгоритма шага 14 на TypeScript (HMAC-SHA256, ключ `WebAppData` + bot token, `data_check_string` из отсортированных ключей). Токен берётся из `TELEGRAM_BOT_TOKEN` окружения тестового стенда, не из фронта. На local/dev это тот же `.env`, что у backend.

Инъекция до загрузки Angular:

```typescript
await page.addInitScript((initData: string) => {
  Object.defineProperty(window, 'Telegram', {
    value: {
      WebApp: {
        initData,
        initDataUnsafe: {},
        ready: () => undefined,
        expand: () => undefined,
        close: () => undefined,
        colorScheme: 'light',
      },
    },
  });
}, initData);
```

Не добавляйте в backend «магический» bypass auth для E2E. Подпись настоящая, Telegram не участвует.

**E2E 1 — onboarding → тема → слово → meaning**

1. Открыть `/`, пройти onboarding (English / Русский / A2).
2. Создать тему, например «Книги».
3. Добавить `bank`, дождаться списка meanings.
4. Выбрать значение, сохранить.
5. В теме видна карточка, статус не пустой (`PENDING` / `ENRICHING` / `READY` — любой, главное не ошибка экрана).

DictionaryProvider в E2E: тот же FakeDictionaryProvider, что в pytest, когда `APP_ENV=local` и `YANDEX_DICTIONARY_API_KEY` пустой. Живой Яндекс допустим, но тест зависит от сети. Обхода auth нет.

**E2E 2 — занятие до конца**

Тема с 3 готовыми (`READY`) словами. Старт random → introduction → matching → sentence → definition → экран завершения. Для фразы sentence пропускается — отдельный прогон или слово+фраза в той же теме.

**E2E 3 — close/reopen**

Начать занятие, пройти introduction, закрыть контекст браузера, открыть снова с тем же `initData` (тот же Telegram user id). Приложение предлагает продолжить, этап не introduction, а следующий сохранённый. `current_stage` в БД совпадает.

Для E2E 3 не чистите `localStorage` между заходами в одном тесте; JWT должен пережить reopen. Между тестами — изолированный `telegram_user_id`, чтобы не делить словарь.

Команды:

```bash
cd infra
docker compose --env-file ../.env up -d
cd ../e2e
TELEGRAM_BOT_TOKEN=... E2E_BASE_URL=http://localhost:8080 npx playwright test
```

В `.github/workflows/ci.yml` добавьте job `e2e` после `backend`/`frontend`: поднять postgres/redis/backend/frontend/nginx (как docker job, либо compose), прогнать Playwright. Секреты bot token для CI — GitHub Actions `secrets.TELEGRAM_BOT_TOKEN` (тестовый бот или тот же dev-токен). Не коммитьте токен.

### Проверка

Три spec-файла зелёные локально. Падение E2E 3 чаще всего значит, что шаг 57 не пишет `current_stage` на сервер — чините store/API, не тест.

### Коммит

`test(e2e): add playwright flows for capture study and restore`

---

## Шаг 65. Health, ready, Docker healthchecks, логи

### Цель

Проверить и усилить то, что уже сделано на шагах 8, 9, 10, 17, 23: процесс отвечает `/health`, готовность — `/ready`, контейнеры не принимают трафик пока не healthy, логи JSON с `correlation_id`, Celery видит тот же id, секреты в лог не попадают.

### Файлы

```text
backend/app/main.py
backend/app/common/logging.py
backend/app/common/request_context.py
backend/app/enrichment/tasks.py
infra/docker-compose.yml
infra/nginx/nginx.conf
```

### Действия

Чеклист, не переписывание с нуля.

**HTTP**

* `GET /health` → `{"status":"ok"}`, без БД и Redis.
* `GET /ready` → 200 только если postgres `select 1` и Redis `PING` успешны, иначе 503 и `"checks":{"database":...,"redis":...}`.
* Nginx проксирует `/health` и `/ready` на backend (шаг 23).

**Docker healthchecks** — добавьте тем, у кого их ещё нет:

```yaml
  backend:
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/health"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 20s

  celery-worker:
    healthcheck:
      test: ["CMD", "celery", "-A", "app.common.celery_app:celery_app", "inspect", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 25s

  nginx:
    depends_on:
      backend:
        condition: service_healthy
      frontend:
        condition: service_started
```

`frontend` на базе nginx: `wget`/`wget -qO- http://127.0.0.1/` или `curl`. Не ставьте `/ready` frontend-контейнеру — это не API.

**Логи**

* access-middleware шага 8 пишет `method`, `path`, `status_code`, `duration_ms`, `correlation_id`;
* клиентский `X-Correlation-ID` принимается, иначе UUID;
* ответ всегда отдаёт заголовок;
* Celery-задача enrichment в начале вызывает `set_correlation_id` из kwargs или заголовка сообщения. Если HTTP-слой кладёт id в `enrich_vocabulary_item.delay(..., correlation_id=...)` — worker логирует тем же ключом;
* фильтр: не логировать `Authorization`, `init_data`, `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `POSTGRES_PASSWORD`.

Проверьте `JsonLogFormatter`: extra-поля провайдера (`provider`, `operation`) остаются. `print()` в app-коде быть не должно — `rg 'print\\(' backend/app`.

**Nginx** — `log_format json_combined` уже содержит `correlation_id` (шаг 23). Убедитесь, что production-конфиг шага 68 копирует тот же format.

### Проверка

```bash
cd infra
docker compose ps
curl -si http://localhost:8080/health | grep -i correlation
curl -s http://localhost:8080/ready | python3 -m json.tool
docker compose stop redis
curl -si http://localhost:8080/ready | head -1
docker compose start redis
```

`/ready` без Redis — 503. `backend` в `docker compose ps` — `healthy`. Лог ошибки lookup содержит `correlation_id` и не содержит ключ OpenAI.

```bash
docker compose logs --no-color backend | grep '"level":"ERROR"' | head
```

### Коммит

`chore(infra): harden healthchecks and correlation id across workers`

---

## Шаг 66. Резервные копии PostgreSQL

### Цель

Раз в сутки `pg_dump` в custom-формате (`-Fc`), хранятся несколько последних копий, один раз на этой неделе выполнен restore drill. Резервная копия, которую не восстанавливали, копией не считается.

### Файлы

```text
infra/scripts/backup-postgres.sh
infra/scripts/restore-postgres.sh
infra/scripts/backup-cron
```

Каталог `backups/` уже в `.gitignore` (шаг 3).

### Действия

`backup-postgres.sh` запускается на хосте, где крутится compose. Не кладите пароль в argv — берите из `.env`.

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR/infra"

KEEP_COPIES="${BACKUP_KEEP_COPIES:-7}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
mkdir -p "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/vocabulary-$STAMP.dump"

docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$FILE"

find "$BACKUP_DIR" -name 'vocabulary-*.dump' -type f \
  | sort \
  | head -n "-$KEEP_COPIES" \
  | xargs -r rm -f

echo "wrote $FILE"
```

Скрипт: `set -a; source ../.env`. Ротация: оставить 7 последних `vocabulary-*.dump` (GNU `head` на VPS).

`restore-postgres.sh` восстанавливает в **отдельную** БД `vocabulary_restore`, не в боевую:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -c "create database vocabulary_restore;"
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d vocabulary_restore --clean --if-exists < "$1"
docker compose exec postgres psql -U "$POSTGRES_USER" -d vocabulary_restore -c \
  "select (select count(*) from users) as users, (select count(*) from lexemes) as lexemes;"
docker compose exec -T postgres psql -U "$POSTGRES_USER" -c "drop database vocabulary_restore;"
```

Боевой restore — процедура из [11-troubleshooting.md](11-troubleshooting.md), раздел «Резервная копия и восстановление». На шаге 66 вы обязаны прогнать drill один раз.

Cron на VPS (шаг 67/68), не на ноутбуке как единственная копия:

```cron
5 3 * * * /opt/vocabulary-app/infra/scripts/backup-postgres.sh >> /var/log/vocabulary-backup.log 2>&1
```

Семь копий — разумный минимум плана «хранить несколько последних». Object storage не требуется в MVP.

### Проверка

```bash
chmod +x infra/scripts/backup-postgres.sh infra/scripts/restore-postgres.sh
cd infra
set -a && source ../.env && set +a
./scripts/backup-postgres.sh
ls -lh ../backups
./scripts/restore-postgres.sh ../backups/vocabulary-*.dump
```

Dump не нулевого размера. Restore-запрос вернул ненулевой `lexemes`, если вы уже добавляли слова. `drop database vocabulary_restore` прошёл.

### Коммит

`feat(infra): add daily pg_dump and restore drill scripts`

---

## Шаг 67. VPS, домен, HTTPS

### Цель

Сервер доступен по своему домену по HTTPS. Сертификат Let's Encrypt, Nginx терминирует TLS. Postgres и Redis снаружи не слушаются.

### Файлы

На сервере, не в git: `/opt/vocabulary-app/.env`. В репозитории: заготовка `infra/nginx/nginx.prod.conf`.

### Действия

Минимальный VPS: 2 GB RAM (Celery + Postgres + Node-сборка образов тяжелее 1 GB). Ubuntu 24.04.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

A-запись домена на IP VPS. Пока DNS не сходится, certbot не выпускает сертификат.

Клон репозитория в `/opt/vocabulary-app`. `.env` с `APP_ENV=production`, `APP_DEBUG=false`, `MINI_APP_URL=https://YOUR_DOMAIN`, сильным `SECRET_KEY`, боевыми ключами. Файл `chmod 600`.

`nginx.prod.conf`: скопируйте `upstream` и `location /api/`, `/health`, `/ready`, `/media/`, `/` из шага 23. Добавьте TLS и ACME:

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name YOUR_DOMAIN;

    ssl_certificate     /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem;
    add_header Strict-Transport-Security "max-age=31536000" always;
    client_max_body_size 1m;
}
```

Выпуск сертификата (webroot, каталог смонтирован в nginx и certbot):

```bash
mkdir -p /var/www/certbot
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot -d YOUR_DOMAIN --email YOUR_EMAIL --agree-tos --no-eff-email
```

Renew: `0 4 * * * docker compose -f /opt/vocabulary-app/infra/docker-compose.prod.yml run --rm certbot renew && docker compose ... exec nginx nginx -s reload`.

Пока сертификата нет, шаг 68 всё равно поднимает HTTP-only только на localhost — наружу 80/443 после появления файлов сертификата.

### Проверка

```bash
curl -sI https://YOUR_DOMAIN/health
curl -s https://YOUR_DOMAIN/ready
```

Код 200, сертификат не self-signed. `http://` редиректит на `https://`. С ноутбука `nc YOUR_DOMAIN 5432` не открывается.

### Коммит

`feat(infra): add production nginx tls config`

---

## Шаг 68. Production docker compose и скрипт деплоя

### Цель

Отдельный compose без bind-mount исходников, без `--reload`, без публикации 5432/6379. Деплой **ручной**: merge в `main` сам по себе ничего не выкатывает. Это продуктовое решение плана («manual deploy pipeline»).

### Файлы

```text
infra/docker-compose.prod.yml
infra/scripts/deploy.sh
```

### Действия

`docker-compose.prod.yml` — те же сервисы, что local, отличия:

* `APP_ENV=production`, нет volume `../backend/app`;
* backend command без `--reload`;
* postgres/redis `ports` нет;
* nginx слушает 80 и 443, монтирует `nginx.prod.conf`, сертификаты, webroot;
* `restart: unless-stopped`;
* celery тот же `--concurrency=2`;
* `media-data` общий у worker и nginx.

Миграции — явно в скрипте, не «надеемся, что контейнер сделает». Авто-upgrade в entrypoint не добавляйте: падающая миграция при рестарте worker опаснее ручного шага.

`infra/scripts/deploy.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

git pull --ff-only origin main

cd infra
docker compose -f docker-compose.prod.yml --env-file ../.env build
docker compose -f docker-compose.prod.yml --env-file ../.env up -d
docker compose -f docker-compose.prod.yml --env-file ../.env exec backend \
  alembic upgrade head

sleep 3
curl -fsS "https://YOUR_DOMAIN/ready"
curl -fsS "https://YOUR_DOMAIN/health"
```

`--ff-only` — не создавать merge-коммит на сервере при расхождении. Если pull не fast-forward, останавливайтесь и разбирайте.

Не вызывайте этот скрипт из GitHub Actions. CI шага 24 проверяет тесты и сборку образов, выкладка — SSH и `./infra/scripts/deploy.sh`.

Откат: checkout предыдущего тега/коммита, снова `up -d --build`, `/ready`. Схему вниз — только если новая миграция ломает старый код, и после свежего dump (troubleshooting).

### Проверка

На VPS:

```bash
chmod +x infra/scripts/deploy.sh
./infra/scripts/deploy.sh
docker compose -f infra/docker-compose.prod.yml ps
```

Все сервисы `running`/`healthy`. `ss -lntp | grep 5432` пусто снаружи. Повторный запуск скрипта идемпотентен.

### Коммит

`feat(infra): add production compose and manual deploy script`

---

## Шаг 69. Переключение Mini App на production и smoke-тест

### Цель

BotFather и `MINI_APP_URL` указывают на HTTPS-домен. Автор проходит критерии MVP руками, не по памяти.

### Файлы

`.env` на сервере (`MINI_APP_URL`). Код не обязателен, если URL только в env бота.

### Действия

1. `MINI_APP_URL=https://YOUR_DOMAIN` в серверном `.env`, `docker compose ... restart telegram-bot backend`.
2. BotFather → `/mybots` → бот → Bot Settings → Menu Button → URL production. Старый tunnel cloudflared больше не используется.
3. `/setdomain` если BotFather просит domain для Web App — тот же хост без пути.

Smoke — живой проход, чеклист шага 71. Минимум сейчас:

* `/start` → кнопка открывает Mini App с production URL (в шапке Telegram не localhost и не trycloudflare);
* auth 200, пользователь в postgres;
* onboarding (если новый аккаунт) или главный экран;
* создать тему, добавить word, выбрать meaning, дождаться карточки;
* добавить phrase;
* пройти занятие и закрыть/открыть незавершённую сессию;
* irregular verbs открываются;
* удаление аккаунта на отдельном тестовом пользователе, не на основном, если не хотите терять словарь.

Смотрите логи:

```bash
docker compose -f docker-compose.prod.yml logs --tail=100 backend celery-worker nginx
```

Нет 500 на главных путях. Enrichment доходит до `READY` или `PARTIAL`, не зависает в `ENRICHING`.

### Проверка

`curl -s https://YOUR_DOMAIN/ready` с телефона в LTE, не только с VPS localhost. Mini App открывается в Telegram iOS и Android по возможности: WebView разный, audio mp3 проверяется на iOS отдельно (ogg на шаге 32 уже конвертируется).

### Коммит

`chore: point mini app url to production domain`

Если менялся только серверный `.env` — коммита нет, зафиксируйте URL в `docs/architecture.md` на следующем шаге.

---

## Шаг 70. README и документация архитектуры

### Цель

Четыре файла из структуры monorepo плана плюс корневой README, по которому можно поднять проект без чтения всех 72 шагов.

### Файлы

```text
README.md
docs/architecture.md
docs/api.md
docs/data-model.md
docs/post-mvp.md
```

`docs/implementation/*` уже есть — из README на них ссылка «пошаговый план». Не копируйте туда недели 1–4 целиком.

### Действия

**README.md** — что это (Mini App, ru→en), структура, имена env (не значения), `docker compose` + alembic, тесты, ручной `deploy.sh`, ссылки на docs.

**docs/architecture.md** — модульный монолит; модули backend включая `analytics`; провайдеры; enrichment lock+unique; фронт features/signals; initData→JWT.

**docs/api.md** — все `/api/v1/...` из плана §19, включая DELETE users/me; коды 401/404/422/429; формат ошибки шага 61.

**docs/data-model.md** — таблицы §12, общее vs персональное §13, unique-ключи, что каскадится с аккаунтом.

**docs/post-mvp.md** — очередь из §38–39 и §6: MediaAsset, Sentry, Grafana, TTS, SRS, статистика, mobile, teacher/student. Не ТЗ на реализацию.

### Проверка

Человек, не читавший чат, по README поднимает compose и находит DELETE `/users/me` в `api.md`. В `post-mvp.md` есть Sentry и SRS. В коде их нет:

```bash
rg -n "sentry|Sentry|fsrs|MediaAsset" backend/app frontend/src || true
```

Пусто (или только упоминание в docs).

### Коммит

`docs: add readme architecture api data-model and post-mvp`

---

## Шаг 71. Сверка с критериями готовности MVP

### Цель

Двадцать пунктов раздела 42 плана отмечены по факту, не по намерению. Пункт без доказательства — не выполнен.

### Файлы

Не обязательно. Можно чеклист в конце `docs/architecture.md` или оставить только прохождение ниже.

### Действия

Идите сверху вниз. Для каждого пункта — где смотрели (URL, SQL, лог, тест).

| # | Критерий | Как подтвердить |
| --- | --- | --- |
| 1 | Mini App открывается через Telegram | `/start`, production URL |
| 2 | Onboarding | строка `users.onboarding_completed_at`, событие `onboarding_completed` |
| 3 | Создаёт тему | `collections`, событие `collection_created` |
| 4 | Добавляет word | `user_vocabulary_items` + `lexemes.type = word` |
| 5 | Добавляет phrase | то же, `type = phrase`, не больше 5 слов |
| 6 | Выбирает Meaning | `meaning_id` на карточке |
| 7 | Перевод | `translations` на полной карточке |
| 8 | IPA | поле lexeme/карточки, если словарь дал |
| 9 | Audio если доступно | `audio_url`, воспроизведение в Mini App |
| 10 | AI definition/example | `meaning_contents` или `PARTIAL` без молчаливой пустоты |
| 11 | Открывает карточку | `GET /api/v1/vocabulary/{id}` в UI |
| 12 | Запускает занятие | `study_sessions`, `study_started` |
| 13 | Word flow | четыре этапа |
| 14 | Phrase flow | без sentence |
| 15 | Irregular verbs flow | системная тема, формы |
| 16 | Сессия восстанавливается | E2E 3 и ручной close/reopen |
| 17 | Данные не теряются | повторный вход, тот же словарь |
| 18 | PostgreSQL backup | dump на диске + restore drill шага 66 |
| 19 | Production развёрнут | HTTPS `/ready` |
| 20 | Критические тесты проходят | CI зелёный, pytest + Vitest + 3 E2E |

Пункты 8–10 допускают деградацию: нет IPA/audio — карточка жива (`PARTIAL`). Нет перевода — сценарий не выполнен. Нет meaning — не выполнен.

Если пункт красный — возвращайтесь на неделю 2/3, не маскируйте skip-тестом.

### Проверка

Двадцать «да». Нет «почти».

### Коммит

`chore: record mvp readiness checklist`

Коммит только если чеклист реально попал в репозиторий. Иначе шаг без коммита.

---

## Шаг 72. Итоги и вход в post-MVP

### Цель

Неделя 4 закрыта. Очередь после MVP записана. Код изображений, Sentry и SRS **не пишется**.

### Файлы

`docs/post-mvp.md` (дополнить итогами), при желании короткий абзац в корневом README «Статус: MVP для ежедневного использования автором».

### Действия

Зафиксируйте факт:

* production Mini App работает;
* бэкап есть и восстанавливался;
* события пишутся;
* аккаунт удаляется без общего лексикона;
* лимиты: Redis, 50 AI/сутки, Celery concurrency 2;
* тесты критичных путей зелёные.

Первая очередь **не реализовывать сейчас** (план §39 Post-MVP 1 и P2 backlog):

1. правки UX после собственного недельного использования;
2. Sentry (frontend + backend + Celery);
3. Grafana/Prometheus;
4. TTS fallback, если Wikimedia молчит;
5. архитектура изображений / MediaAsset;
6. staging-окружение отдельно от production.

Retention (SRS, streak, reminders) — ещё позже, после гипотезы «возвращаются через неделю».

Не оставляйте в коде `TODO: add sentry`. Нет закомментированных интеграций.

### Проверка

`docs/post-mvp.md` существует и читается как очередь. `rg sentry backend/app` пусто. Definition of Done недели ниже — все пункты.

### Коммит

`docs: close mvp week and record post-mvp entry points`

---

## Definition of Done недели 4

Проверьте каждый пункт вживую:

- [ ] Production Mini App открывается из Telegram по HTTPS
- [ ] Auth проходит, данные пишутся в PostgreSQL
- [ ] Onboarding, тема, word, phrase, выбор Meaning работают на production
- [ ] Enrichment доводит карточку до `READY` или честного `PARTIAL`
- [ ] Занятие (word, phrase, irregular verbs) проходит до конца
- [ ] Незавершённая сессия продолжается после закрытия Telegram
- [ ] События `onboarding_completed`, `collection_created`, `word_added`, `study_started`, `study_stage_completed`, `study_completed` пишутся из сервисов
- [ ] `DELETE /api/v1/users/me` удаляет персональные таблицы и оставляет Lexeme/Meaning/Translation/MeaningContent
- [ ] 429 на превышении частоты, суточный AI-лимит 50, Celery concurrency 2
- [ ] Доменные исключения → HTTP, фронт показывает `ApiError`, пустых catch нет
- [ ] pytest критичных сценариев зелёный (см. [10-testing-reference.md](10-testing-reference.md))
- [ ] Vitest: этапы, 3 попытки, phrase skip, matching, restore
- [ ] Три Playwright E2E зелёные
- [ ] `/health` 200, `/ready` падает при остановке Redis, контейнеры healthcheck
- [ ] JSON-логи с `correlation_id` на API и worker
- [ ] `pg_dump` лежит на диске, restore drill выполнен
- [ ] Деплой только ручным `deploy.sh`, CI не выкатывает после merge
- [ ] README + `docs/architecture.md`, `api.md`, `data-model.md`, `post-mvp.md`
- [ ] 20 критериев раздела 42 отмечены по факту
- [ ] Изображения, Sentry, SRS в коде отсутствуют

### Если неделя затянулась

Режьте в порядке из [README плана реализации](README.md): E2E до одного сценария, не бэкапы и не initData. Не выкатывайте production без dump-скрипта и без DELETE аккаунта, если собираетесь звать внешних людей.

Дальше — пользование автором (этап 0 проверки спроса). Код следующей волны только из `docs/post-mvp.md`.
