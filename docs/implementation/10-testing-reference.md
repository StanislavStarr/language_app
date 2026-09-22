# Справочник: тестирование

Как организовать тесты English Vocabulary App и **что** обязательно покрыть. Шаги, когда тесты появляются в плане: 14 (Telegram), 27 (нормализация), 44 (отбор слов), 62–64 (полный набор). CI уже гоняет pytest и Vitest с шага 24 — этот файл не про пайплайн, а про каталог сценариев и рабочие образцы.

Продуктовый план §31 и правила проекта §36 — источник обязательных кейсов. Если теста нет в списке ниже, его можно не писать. Если есть — skip в CI недопустим.

---

## 1. Три слоя и чем они не являются

| Слой | Инструмент | Что доказывает | Чего не делает |
| --- | --- | --- | --- |
| Backend unit / component | pytest + pytest-asyncio | правило домена на реальном Postgres и Redis, с фейковыми провайдерами | не ходит в Yandex, Wiktionary, OpenAI, Wikimedia |
| Frontend unit | Vitest (раннер Angular 22; Karma удалена) | store занятия, чистые функции этапов | не открывает Telegram |
| E2E | Playwright | три пользовательских пути через nginx | не заменяет unit-тесты matching и HMAC |

Интеграция backend (HTTP + БД + Redis + Celery без внешних API) живёт в том же pytest: `httpx.AsyncClient` по ASGI, брокер — Redis из CI. Отдельный «integration package» не заводим.

SQLite в тестах нет: нужны `pg_trgm`, `JSONB`, `UUID`, native enum, unique constraints как в production.

---

## 2. Backend: стек и запуск

Зависимости уже в `backend/pyproject.toml` (шаг 7):

* `pytest`
* `pytest-asyncio` (`asyncio_mode = auto`)
* `httpx` (клиент приложения)

Postgres и Redis:

* локально — `infra/docker-compose.yml`, порты 5432 и 6379 как на шаге 9;
* CI — `services:` в `.github/workflows/ci.yml` (шаг 24), база `vocabulary_test`;
* testcontainers — допустимая альтернатива, если не хотите зависеть от compose на ноутбуке. Не дублируйте оба подхода в одном `conftest.py`. Предпочтение плана: те же переменные, что CI (`POSTGRES_HOST=localhost`, `POSTGRES_DB=vocabulary_test` или `vocabulary`).

```bash
cd infra
docker compose up -d postgres redis
cd ../backend
POSTGRES_HOST=localhost uv run alembic upgrade head
POSTGRES_HOST=localhost uv run pytest -v
POSTGRES_HOST=localhost uv run pytest -k normalization -v
```

Миграции на чистую БД должны проходить — это уже job CI «Migrations apply cleanly». Тесты, которые сами вызывают `create_all`, обходят Alembic и пропускают `pg_trgm` — так не пишите.

Провайдеры подменяются в composition root теста, не через `unittest.mock.patch` всего модуля `openai`. Класс на 15 строк, реализующий протокол, — канонический способ (primer §9).

---

## 3. Frontend: Vitest

```bash
cd frontend
npx ng test
npx ng test --watch=false
npx ng test --watch=false --include=src/app/features/study/study-session-store.spec.ts
```

CI шага 24: `npm test -- --watch=false`. Новые `*.spec.ts` подхватываются.

Имена: рядом с исходником, `study-session-store.spec.ts` для `study-session-store.ts`. Не складывайте все тесты в `frontend/src/app/tests/`.

Zoneless Angular 22: если TestBed ругается на change detection, в `configureTestingModule` добавьте `provideZonelessChangeDetection()` — тот же провайдер, что в `app.config.ts`.

---

## 4. E2E: Playwright

Каталог `e2e/` (шаг 64), не внутри unit-конфига Angular.

```bash
cd infra && docker compose --env-file ../.env up -d
cd ../e2e
TELEGRAM_BOT_TOKEN=... E2E_BASE_URL=http://localhost:8080 npx playwright test
```

Три файла:

| Файл | Сценарий плана |
| --- | --- |
| `onboarding-add-word.spec.ts` | onboarding → тема → слово → выбор Meaning |
| `study-finish.spec.ts` | тема → старт → все этапы → завершение |
| `session-restore.spec.ts` | close/reopen → продолжение `in_progress` |

Telegram как приложение не запускается. `initData` подписывается HMAC и инжектится в `window.Telegram.WebApp` до загрузки бандла. Backend остаётся с полной проверкой подписи — обхода auth для E2E нет.

На local/dev пустой `YANDEX_DICTIONARY_API_KEY` должен включать FakeDictionaryProvider, иначе E2E 1 зависит от сети. Не вводите `SKIP_AUTH=true`.

---

## 5. Обязательные backend-сценарии

Каждый пункт — наблюдаемое поведение, не «метод вызван».

### 5.1. Normalization

Файл: `tests/test_normalization.py`. Чистая функция шага 27.

* `"  Clarify  "` и `"clarify"` дают один `normalized_text`;
* регистр не создаёт второй `Lexeme`;
* несколько пробелов внутри фразы схлопываются;
* тип `phrase`, если после нормализации слов больше одного;
* тип `word` для одного токена;
* уникальность `(language_id, normalized_text)`: второй insert ловится IntegrityError / доменной ошибкой дубликата, в таблице одна строка.

### 5.2. Duplicate prevention

Файл: `tests/test_duplicate_prevention.py`.

* два `POST /api/v1/vocabulary` с одним `meaning_id` одного пользователя: вторая операция не создаёт второй `UserVocabularyItem` (unique `user_id + meaning_id`);
* тот же meaning во второй теме: один item, два `CollectionItem`;
* пользователь B добавляет тот же meaning — вторая строка `user_vocabulary_items`, общий `meanings.id` один;
* удаление из темы не удаляет `UserVocabularyItem`, если он ещё в «Все слова» / другой теме (поведение недели 2 — зафиксируйте фактический контракт и тестируйте его).

### 5.3. Typo suggestion

Файл: `tests/test_typo_suggestion.py`. Нужен `pg_trgm`.

* в базе есть `clarify`, запрос `clarfy` возвращает suggestion, список meanings может быть пустым;
* точное `clarify` suggestion не содержит;
* неизвестный набор букв без похожих лексем — стабильный пустой ответ, не 500.

### 5.4. Random / new-first selection

Файл: `tests/test_study_selection.py`.

* random не выбирает `PENDING` / `ENRICHING`;
* `PARTIAL` и `READY` участвуют, если так решили на неделе 3 — один явный тест на границу;
* new-first: `last_studied_at IS NULL` раньше тех, кто уже учился;
* manual: порядок id из тела запроса сохраняется в `StudySessionItem.position`;
* запрос количества больше, чем готовых карточек — ошибка валидации, не урезанная пачка молча (если сервис так задокументирован) либо урезанная пачка — главное, поведение одно и покрыто.

### 5.5. Dictionary fallback

Файл: `tests/test_lookup_fallback.py`.

* primary вернул пустой `entries` → вызывается fallback, primary больше не дергается;
* primary вернул перевод без IPA, fallback вернул IPA → в результате IPA есть, переводы primary не затёрты;
* primary бросил временную ошибку, fallback успешен → клиент получает meanings, не 503;
* оба бросили → переход к AI fallback значений (следующий пункт), не необработанное исключение.

Счётчик вызовов на фейках: `lookup_calls: list[str]`.

### 5.6. AI fallback

Файл: `tests/test_ai_fallback.py`.

* словари вернули ≥1 meaning — `AIProvider.generate_meanings` не вызывается;
* словари пусты — вызывается AI fallback значений;
* пользовательский сценарий «нет нужного значения» с `source_context` передаёт контекст в AI и **не** сохраняет его в `MeaningContent.definition` / `example`;
* исчерпан суточный лимит — AI не вызывается, доменная `AiDailyLimitExceededError` (шаг 60).

### 5.7. Enrichment status

Файл: `tests/test_enrichment_status.py`. Вызывать `EnrichmentService`, не Celery.

* dictionary + audio + AI definition/example → `READY`;
* нет audio, остальное есть → `PARTIAL`, item можно отдать в занятие, если так сделано на неделе 2;
* AI упал после ретраев, перевод есть → не `ENRICHING`, статус терминальный (`PARTIAL` или `FAILED`);
* повторный прогон `READY` карточки ничего не регенерирует (кэш MeaningContent).

### 5.8. Retry

Файл: `tests/test_enrichment_retry.py`.

* `ProviderTemporaryError` на AI → задача планирует retry с `countdown == 10, 20, 40` для retries 0, 1, 2;
* `max_retries=3`, четвёртая попытка не идёт в провайдер;
* `ProviderPermanentError` / валидация structured output — retry нет, статус терминальный.

Сам декоратор Celery можно проверить через вызов `run_async_task` и фейк с счётчиком; брокер не обязателен. Один тест с `.delay()` + Redis — по желанию, не вместо unit на сервисе.

### 5.9. Telegram auth

Файл: `tests/test_telegram_auth.py` (шаг 14). Не удалять. Обязательные шесть кейсов — раздел 8 ниже.

### 5.10. Product events и delete account

Появились на шагах 58–59, тоже критичны перед внешними людьми:

* первое завершение onboarding → одна строка `onboarding_completed`;
* повторный PATCH профиля → новых событий нет;
* `DELETE /users/me` оставляет `lexemes` / `meanings` / `translations` / `meaning_contents`.

### 5.11. Идемпотентность enrichment

Раздел 9. Unique `(meaning_id, cefr_level, prompt_version)` + Redis `SET NX EX`. Два параллельных запуска — один AI-вызов, одна строка.

---

## 6. Обязательные frontend-сценарии

Файл-якорь: `frontend/src/app/features/study/study-session-store.spec.ts`. Чистые функции — соседние spec.

### 6.1. Состояние занятия и переходы этапов

Word-сессия из ≥2 карточек:

* после `start` → stage `introduction`, index 0;
* конец introduction → `matching`;
* все верные пары → `sentence`;
* все sentence → `definition`;
* все definition → `completed` и вызов complete API.

Не проверяйте порядок CSS-классов.

### 6.2. Три попытки

Этапы sentence и definition, строгая проверка (план §8.2):

* 1-я и 2-я ошибка: `attemptCount` растёт, ответ не раскрыт, этап тот же;
* 3-я ошибка: `answerRevealed === true`, показан правильный текст;
* переход дальше сбрасывает попытки;
* успех с первой попытки: reveal нет.

Irregular verbs: та же тройка на вводе `went` / `gone`, если store общий.

### 6.3. Phrase skip

* пачка только `phrase`: после matching сразу `definition`, `sentence` не посещается;
* пачка только `word`: `sentence` есть;
* смешанная: sentence-упражнение строится только по word-элементам.

Это продуктовое правило §8.3, не «оптимизация UI».

### 6.4. Matching

* клик слева + верный справа → пара в множестве найденных, повторно не кликается;
* неверная пара → выбор сбрасывается, никто не блокируется;
* нет DnD (в MVP запрещён).

Логику пар вынесите в чистую функцию — её проще тестировать, чем DOM.

### 6.5. Restore

* ответ `GET /study-sessions/{id}`: `status: in_progress`, `current_stage: sentence`, позиция 2 → store не начинает introduction с нуля;
* `status: completed` → страница занятия не зовёт restore как активную сессию;
* после restore `submitAnswer` идёт в тот же `session.id`.

`StudyApi` — fake с `vi.fn()`.

---

## 7. Фикстуры pytest

Один `backend/tests/conftest.py`. Транзакция на тест + rollback: быстро и изолированно. Если уникальные ограничения и `pg_trgm` мешают вложенным транзакциям — альтернатива: чистая схема + `truncate ... cascade` в `function` фикстуре. Ниже — вариант с rollback, который работает с async SQLAlchemy 2.x, если все записи идут через ту же сессию.

```python
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.tokens import issue_access_token
from app.common.database import get_db_session
from app.common.settings import Settings, get_settings
from app.integrations.ai.provider import (
    AIProvider,
    GeneratedMeaningContent,
    MeaningContentRequest,
)
from app.integrations.dictionary.provider import (
    DictionaryEntry,
    DictionaryLookupRequest,
    DictionaryLookupResult,
    DictionaryMeaning,
    DictionaryProvider,
    DictionaryTranslation,
    PartOfSpeech,
)
from app.main import create_app
from app.users.models import CefrLevel, User


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
async def db_session(settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = factory(bind=connection)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def fake_dictionary_provider() -> FakeDictionaryProvider:
    return FakeDictionaryProvider()


@pytest.fixture
def fake_ai_provider() -> FakeAIProvider:
    return FakeAIProvider()


@pytest.fixture
async def app(
    db_session: AsyncSession,
    fake_dictionary_provider: FakeDictionaryProvider,
    fake_ai_provider: FakeAIProvider,
    settings: Settings,
):
    application = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_session
    application.state.dictionary_provider = fake_dictionary_provider
    application.state.ai_provider = fake_ai_provider
    return application


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    account = User(
        native_language_id=2,
        learning_language_id=1,
        cefr_level=CefrLevel.A2,
        onboarding_completed_at=datetime.now(UTC),
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.fixture
def auth_headers(user: User, settings: Settings) -> dict[str, str]:
    token = issue_access_token(
        user_id=user.id,
        secret_key=settings.secret_key,
        ttl_days=settings.access_token_ttl_days,
    )
    return {"Authorization": f"Bearer {token}"}
```

Подключение фейков к сервисам должно совпадать с production composition: если lookup берёт провайдеров из FastAPI `Depends`, переопределяйте Depends. Если из `app.state` — пишите в `state` как выше. Не оставляйте два способа сразу.

Фейки:

```python
class FakeDictionaryProvider:
    name = "fake-dictionary"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.result = DictionaryLookupResult(provider_name=self.name, entries=())

    async def lookup(self, request: DictionaryLookupRequest) -> DictionaryLookupResult:
        self.calls.append(request.text)
        return self.result


def bank_entry() -> DictionaryEntry:
    return DictionaryEntry(
        text="bank",
        ipa="bæŋk",
        meanings=(
            DictionaryMeaning(
                part_of_speech=PartOfSpeech.NOUN,
                translations=(
                    DictionaryTranslation(text="берег"),
                    DictionaryTranslation(text="банк"),
                ),
            ),
        ),
    )


class FakeAIProvider:
    name = "fake-ai"

    def __init__(self) -> None:
        self.meaning_content_calls = 0
        self.fallback_calls = 0

    async def generate_meaning_content(
        self, request: MeaningContentRequest
    ) -> GeneratedMeaningContent:
        self.meaning_content_calls += 1
        return GeneratedMeaningContent(
            definition="A place where money is kept.",
            example="She went to the bank.",
        )
```

Сигнатуры должны совпадать с протоколами шагов 29 и 33. Если `AIResult` — обёртка, фейк возвращает её, не сырой dataclass.

HTTP-тест:

```python
import pytest


@pytest.mark.asyncio
async def test_lookup_returns_meanings(
    client: AsyncClient,
    auth_headers: dict[str, str],
    fake_dictionary_provider: FakeDictionaryProvider,
) -> None:
    fake_dictionary_provider.result = DictionaryLookupResult(
        provider_name=fake_dictionary_provider.name,
        entries=(bank_entry(),),
    )

    response = await client.post(
        "/api/v1/lexemes/lookup",
        headers=auth_headers,
        json={"text": "bank"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meanings"]
    assert fake_dictionary_provider.calls == ["bank"]
```

Префикс `/api/v1` должен совпадать с тем, как роутеры примонтированы в `create_app`. Если клиент ходит на `/lexemes/lookup` без префикса — чините фикстуру, не прод.

Языки с seed-миграции шага 13: в тестовой БД после `alembic upgrade head` уже есть `en` и `ru`. Не хардкодьте `native_language_id=2`, если seed не гарантирует id. Надёжнее:

```python
from sqlalchemy import select
from app.languages.models import Language


async def language_id(session: AsyncSession, code: str) -> int:
    result = await session.execute(select(Language.id).where(Language.code == code))
    return result.scalar_one()
```

Redis в тестах лимитов: отдельная DB index (например `REDIS_URL=.../15`) или `flushdb` только тестовой базы в fixture. Не `FLUSHALL` на shared Redis разработчика.

---

## 8. Telegram initData HMAC без Telegram

Настоящий клиент не нужен. Строка `initData` — query string. Подпись: secret = HMAC-SHA256(`WebAppData`, bot_token), hash = HMAC-SHA256(secret, data_check_string). `data_check_string` — пары `key=value` по отсортированным ключам **без** `hash`, через `\n`.

Готовая фабрика уже в шаге 14. Держите её в `tests/telegram_init_data.py` и импортируйте из unit и, зеркально, из Playwright (`e2e/support/telegram-init-data.ts`).

```python
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

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
```

Обязательные проверки `parse_and_verify_init_data`:

| Кейс | Ожидание |
| --- | --- |
| валидная строка | `telegram_user_id == 555_000_111` |
| `corrupt_hash=True` | `TelegramInitDataSignatureInvalid` |
| подпись другим bot token | `TelegramInitDataSignatureInvalid` |
| подмена `user.id` в уже подписанной строке | `TelegramInitDataSignatureInvalid` |
| `auth_date` старше `max_age_seconds` | `TelegramInitDataExpired` |
| нет `hash` | `TelegramInitDataMalformed` |

HTTP-уровень: `POST /api/v1/auth/telegram` с валидной строкой выдаёт JWT, с битой — 401 и одно и то же сообщение (шаг 16). В тесте роутера `settings.telegram_bot_token` равен `BOT_TOKEN` фикстуры.

E2E использует **боевой** `TELEGRAM_BOT_TOKEN` стенда, потому что backend в docker читает `.env`. Не хардкодьте прод-токен в spec-файле.

Для теста «подмена id» замена подстроки зависит от URL-encoding. Если `replace` не попал в `user`, сначала выведите `build_init_data(telegram_user_id=1)` и поправьте якорь. Это тот же совет шага 14.

Timing-safe сравнение уже в реализации (`hmac.compare_digest`). Отдельный тест на timing не пишите.

---

## 9. Идемпотентность enrichment: lock + unique

Два одновременных worker не должны дважды вызвать OpenAI для `(meaning_id, cefr_level, prompt_version)`. Защита двойная (шаг 38, integrations-reference):

1. `UNIQUE` на `meaning_contents`;
2. Redis `SET key NX EX ttl` вокруг генерации.

Тест обязан ломать оба слоя по отдельности и вместе.

Ключ лока: `enrichment:meaning-content:{meaning_id}:{cefr}:{prompt_version}`. TTL больше, чем `task_soft_time_limit` (150 с на шаге 17) — иначе второй worker начнёт генерацию, пока первый ещё работает.

```python
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.enrichment.service import EnrichmentService
from app.lexicon.models import MeaningContent
from app.users.models import CefrLevel


class SlowAIProvider(FakeAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate_meaning_content(self, request: MeaningContentRequest) -> GeneratedMeaningContent:
        self.meaning_content_calls += 1
        self.started.set()
        await self.release.wait()
        return await super().generate_meaning_content(request)


@pytest.mark.asyncio
async def test_parallel_enrichment_calls_ai_once(
    db_session: AsyncSession,
    fake_ai_provider: SlowAIProvider,
    redis_client: Any,
    ready_vocabulary_item: Any,
) -> None:
    service = EnrichmentService(
        session=db_session,
        ai_provider=fake_ai_provider,
        redis=redis_client,
    )

    first = asyncio.create_task(service.enrich_item(ready_vocabulary_item.id))
    await fake_ai_provider.started.wait()
    second = asyncio.create_task(service.enrich_item(ready_vocabulary_item.id))
    fake_ai_provider.release.set()
    await asyncio.gather(first, second)

    count = await db_session.scalar(
        select(func.count()).select_from(MeaningContent).where(
            MeaningContent.meaning_id == ready_vocabulary_item.meaning_id,
            MeaningContent.cefr_level == CefrLevel.A2,
            MeaningContent.prompt_version == "v1",
        )
    )
    assert count == 1
    assert fake_ai_provider.meaning_content_calls == 1
```

Если второй вызов не ждёт lock, а сразу insert — поймайте unique violation и **перечитайте** существующую строку. Тест на этот путь: первый воркер уже закоммитил `MeaningContent`, lock истек или обойдён, второй insert падает, в таблице всё ещё одна строка, `meaning_content_calls` у второго фейка 0 либо 1 в зависимости от того, увидел ли он кэш до AI. Явный инвариант: `count == 1` всегда.

Не мокайте `session.commit` так, чтобы unique никогда не стрелял — тогда тест не проверяет ограничение БД.

Повторная доставка Celery (`task_acks_late`): вызовите `enrich_item` дважды последовательно на уже `READY` item — AI не вызывается. Это дешевле параллельного теста и ловит забытый early-return.

`source_context` пользователя в запрос `MeaningContentRequest` не попадает. Отдельный assert: после enrichment `MeaningContent.definition` не содержит предложение из `source_context`.

---

## 10. TestBed для StudySessionStore

Store создаётся на шаге 50. Тесты — шаг 63. Мокается `StudyApi`, не `HttpClient`: store не должен знать URL.

Минимальный контракт, на который опираются кейсы. Если на неделе 3 имена методов другие — тесты переименуйте, инварианты оставьте.

```typescript
import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { StudyApi } from './study-api';
import { StudySessionStore } from './study-session-store';
import { StudySessionDetail } from './study-session-detail';

const WORD_A = {
  sessionItemId: 'si-1',
  vocabularyItemId: 'vi-1',
  lexemeType: 'word' as const,
  text: 'clarify',
  translation: 'прояснить',
  definition: 'To make something clearer.',
  example: 'Could you clarify what you mean?',
  exampleGap: 'Could you _____ what you mean?',
};

const WORD_B = {
  sessionItemId: 'si-2',
  vocabularyItemId: 'vi-2',
  lexemeType: 'word' as const,
  text: 'avoid',
  translation: 'избегать',
  definition: 'To stay away from something.',
  example: 'Try to avoid junk food.',
  exampleGap: 'Try to _____ junk food.',
};

const PHRASE = {
  sessionItemId: 'si-3',
  vocabularyItemId: 'vi-3',
  lexemeType: 'phrase' as const,
  text: 'on the bank',
  translation: 'на берегу',
  definition: 'At the side of a river.',
  example: 'He sat on the bank.',
  exampleGap: null,
};

function sessionFixture(overrides: Partial<StudySessionDetail> = {}): StudySessionDetail {
  return {
    id: 'session-1',
    status: 'in_progress',
    currentStage: 'introduction',
    currentItemIndex: 0,
    items: [WORD_A, WORD_B],
    ...overrides,
  };
}

describe('StudySessionStore', () => {
  let store: StudySessionStore;
  let studyApi: {
    createSession: ReturnType<typeof vi.fn>;
    getSession: ReturnType<typeof vi.fn>;
    saveProgress: ReturnType<typeof vi.fn>;
    completeSession: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    studyApi = {
      createSession: vi.fn().mockResolvedValue(sessionFixture()),
      getSession: vi.fn(),
      saveProgress: vi.fn().mockResolvedValue(undefined),
      completeSession: vi.fn().mockResolvedValue({ status: 'completed' }),
    };

    TestBed.configureTestingModule({
      providers: [StudySessionStore, { provide: StudyApi, useValue: studyApi }],
    });

    store = TestBed.inject(StudySessionStore);
  });

  it('starts on introduction and reaches matching after all cards', async () => {
    await store.start({ collectionId: 'col-1', itemCount: 2, selectionMode: 'random' });

    expect(store.currentStage()).toBe('introduction');
    store.completeIntroductionItem();
    store.completeIntroductionItem();
    expect(store.currentStage()).toBe('matching');
  });

  it('reveals the answer after three failed attempts', async () => {
    await store.start({ collectionId: 'col-1', itemCount: 2, selectionMode: 'random' });
    store.setStageForTest('sentence');

    store.submitAnswer('wrong');
    store.submitAnswer('wrong');
    expect(store.answerRevealed()).toBe(false);
    store.submitAnswer('wrong');
    expect(store.answerRevealed()).toBe(true);
    expect(store.attemptCount()).toBe(3);
  });

  it('skips sentence stage for phrase-only sessions', async () => {
    studyApi.createSession.mockResolvedValue(
      sessionFixture({ items: [PHRASE], currentStage: 'introduction' }),
    );
    await store.start({ collectionId: 'col-1', itemCount: 1, selectionMode: 'random' });

    store.completeIntroductionItem();
    expect(store.currentStage()).toBe('matching');
    store.completeMatching();
    expect(store.currentStage()).toBe('definition');
  });

  it('restores in-progress sentence stage', async () => {
    studyApi.getSession.mockResolvedValue(
      sessionFixture({ currentStage: 'sentence', currentItemIndex: 1 }),
    );

    await store.restore('session-1');

    expect(store.currentStage()).toBe('sentence');
    expect(store.currentItemIndex()).toBe(1);
    expect(store.sessionId()).toBe('session-1');
  });

  it('marks a correct matching pair and rejects a wrong one', async () => {
    await store.start({ collectionId: 'col-1', itemCount: 2, selectionMode: 'random' });
    store.setStageForTest('matching');

    store.selectEnglish(WORD_A.sessionItemId);
    store.selectTranslation(WORD_B.sessionItemId);
    expect(store.matchedIds().size).toBe(0);

    store.selectEnglish(WORD_A.sessionItemId);
    store.selectTranslation(WORD_A.sessionItemId);
    expect(store.matchedIds().has(WORD_A.sessionItemId)).toBe(true);
  });
});
```

`setStageForTest` не обязателен в проде. Лучше прогнать store через introduction без него. Если introduction требует кликов по N карточкам — вызовите тот же метод, что UI. Тестовый setter допустим только если иначе придётся дублировать половину сессии в каждом кейсе; не экспортируйте его из public API компонента.

`saveProgress` должен вызываться при смене этапа — отдельный assert `toHaveBeenCalledWith`, чтобы restore на backend имел что читать. Это связь с E2E 3.

Проверка ответа — чистая функция, её тестируйте без store:

```typescript
import { describe, expect, it } from 'vitest';
import { isStrictAnswerMatch } from './answer-checking';

describe('isStrictAnswerMatch', () => {
  it('accepts exact lexeme text', () => {
    expect(isStrictAnswerMatch('clarify', 'clarify')).toBe(true);
  });

  it('rejects extra words', () => {
    expect(isStrictAnswerMatch('clarify this', 'clarify')).toBe(false);
  });
});
```

Нормализация пробелов/регистра на фронте должна совпадать с продуктовым «проверка строгая». Если решите принимать `Clarify` — один явный тест, не молчаливая толерантность.

---

## 11. Что не тестировать

* тексты JSON-логов и наличие конкретного extra-ключа, кроме регрессии утечки секрета;
* разметку SCSS и порядок DOM;
* живые Yandex / OpenAI / Wikimedia в unit;
* BotFather, cloudflared, Let's Encrypt;
* NgRx — его нет;
* drag-and-drop matching — его нет.

Celery inspect, docker healthcheck, pg_dump — ручные проверки шагов 65–66, не pytest.

---

## 12. CI

`.github/workflows/ci.yml` шага 24 уже:

* поднимает Postgres 17 и Redis 8;
* `uv run alembic upgrade head`;
* `uv run pytest -v`;
* `npx tsc --noEmit` и `npm test -- --watch=false`.

Новый файл в `backend/tests/` или `*.spec.ts` попадает в CI без правки workflow. Job E2E добавляется на шаге 64 отдельно и не заменяет этот каталог.

Локально перед push недели 4:

```bash
cd backend && POSTGRES_HOST=localhost uv run pytest -v
cd ../frontend && npx ng test --watch=false
cd ../e2e && npx playwright test
```

Красный критичный кейс из разделов 5–6 блокирует шаг 71 (критерий 20 готовности MVP).
