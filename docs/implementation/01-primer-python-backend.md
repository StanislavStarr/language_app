# Ликбез: Python backend (FastAPI, SQLAlchemy, Celery)

Этот файл объясняет конструкции, которые будут встречаться в шагах 7–72. Читать целиком перед неделей 1
не обязательно — достаточно разделов 1–5, остальное можно открывать по мере появления в шагах.

Предполагается, что вы уверенно программируете, но Python и его экосистема не ваш основной стек.
Поэтому здесь нет объяснений про переменные и циклы, но есть объяснения про то, что в Python принято
иначе, чем в TypeScript/C#/Java.

---

## 1. Типизация: она есть, но её не проверяет Python

Python исполняет код, **полностью игнорируя аннотации типов**. Аннотации — это метаданные. Они нужны
трём потребителям:

1. вам и коллегам при чтении;
2. статическому анализатору (`mypy`), который запускается отдельной командой;
3. библиотекам, которые читают аннотации в рантайме — это Pydantic и FastAPI, и для них аннотации
   становятся настоящими правилами валидации.

Третий пункт — самое важное отличие от TypeScript. В TypeScript типы исчезают при компиляции.
В FastAPI аннотация `word: str` в схеме означает, что запрос с числом будет отклонён с кодом 422
автоматически.

Современный синтаксис, который используем в проекте:

```python
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID


def find_translations(meaning_id: int, limit: int = 3) -> Sequence[str]:
    ...


def normalize_text(raw: str | None) -> str:
    ...


class StudyProgress:
    last_studied_at: datetime | None
    user_id: UUID
```

Что здесь важно:

* `str | None` вместо `Optional[str]` — современная запись, читается как union в TypeScript;
* встроенные `list[str]`, `dict[str, int]` вместо `List`, `Dict` из `typing`;
* `Sequence` из `collections.abc` для «любой последовательности только для чтения» — сигнализирует,
  что функция не будет мутировать переданное;
* `...` (литерал `Ellipsis`) — заглушка тела функции, легальный Python.

Проверка типов запускается вручную:

```bash
uv run mypy app
```

В `pyproject.toml` мы включим строгий режим. Правило проекта: `Any` не используется, а если он приходит
из сторонней библиотеки — сужается сразу на границе интеграции.

---

## 2. `async`/`await`: как в JS, но с одной ловушкой

Синтаксис почти идентичен JavaScript:

```python
import httpx


async def fetch_definition(word: str) -> str:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"https://example.com/define/{word}")
        response.raise_for_status()
        return response.json()["definition"]
```

Ловушка одна, но она ломает production: **синхронный вызов внутри `async def` блокирует весь сервер**.
В Node вы бы это тоже почувствовали, но в FastAPI это особенно коварно, потому что многие популярные
библиотеки синхронные.

```python
import time
import requests


async def bad_example() -> None:
    time.sleep(5)                      # блокирует event loop на 5 секунд
    requests.get("https://example.com")  # тоже блокирует


async def good_example() -> None:
    import asyncio
    await asyncio.sleep(5)
    async with httpx.AsyncClient() as client:
        await client.get("https://example.com")
```

Практические правила для проекта:

* HTTP-запросы — только `httpx.AsyncClient`, никогда `requests`;
* работа с БД — только async-сессия SQLAlchemy;
* если нужна действительно блокирующая операция (например, запуск `ffmpeg`), она живёт в Celery-задаче,
  а не в обработчике запроса;
* внутри Celery-задачи, наоборот, можно блокировать сколько угодно — там нет event loop.

`async with` и `async for` — асинхронные версии `with` и `for`. `with` в Python — это гарантированное
освобождение ресурса, аналог `try/finally` или `using` в C#.

---

## 3. Pydantic: схемы как исполняемый контракт

Pydantic v2 — библиотека валидации. Класс, унаследованный от `BaseModel`, превращает аннотации
в проверки и преобразования.

```python
from pydantic import BaseModel, Field


class LexemeLookupRequest(BaseModel):
    text: str = Field(min_length=1, max_length=80)
    source_context: str | None = Field(default=None, max_length=500)
```

Что происходит при `LexemeLookupRequest(**payload)`:

* отсутствие `text` → ошибка валидации;
* `text` длиной 200 символов → ошибка валидации;
* `text=123` → ошибка (Pydantic v2 по умолчанию не приводит число к строке);
* `source_context` отсутствует → подставится `None`.

В FastAPI такую модель достаточно указать как аннотацию параметра, и валидация станет частью API:
неверный запрос вернёт 422 с описанием проблемного поля, и код обработчика до этого даже не дойдёт.

Три вещи, которые понадобятся в проекте:

**Валидатор поля** — для нормализации ввода:

```python
from pydantic import BaseModel, field_validator


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=300)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned
```

**Чтение из ORM-объекта** — для ответов API:

```python
from pydantic import BaseModel, ConfigDict


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_system: bool
```

`from_attributes=True` разрешает `CollectionResponse.model_validate(collection_orm_object)`.
Это единственный правильный способ отдать данные наружу: ORM-модели никогда не возвращаются из
эндпоинтов напрямую.

**Настройки приложения** — отдельный пакет `pydantic-settings`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str
    postgres_host: str
    postgres_port: int = 5432
```

Имена полей сопоставляются с переменными окружения без учёта регистра: `secret_key` ← `SECRET_KEY`.
Если обязательной переменной нет, приложение падает при старте с понятным сообщением — это правильное
поведение, лучше чем `None` где-то в середине запроса.

Про enum-поля: для закрытых наборов состояний используем `StrEnum`, а не строки.

```python
from enum import StrEnum


class EnrichmentStatus(StrEnum):
    PENDING = "PENDING"
    ENRICHING = "ENRICHING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
```

`StrEnum` наследуется от `str`, поэтому такое значение сериализуется в JSON как обычная строка и
сравнивается со строкой, но опечатка в имени члена — ошибка на этапе проверки типов.

---

## 4. FastAPI: роутеры и зависимости

Минимальное приложение:

```python
from fastapi import FastAPI

app = FastAPI(title="English Vocabulary API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

Запуск:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

`app.main:app` — путь «модуль:объект». `--reload` перезапускает при изменении файлов.
Интерактивная документация появится на `http://localhost:8000/docs` — она генерируется из аннотаций
и схем автоматически, отдельного описания OpenAPI писать не нужно.

### Роутеры

Эндпоинты группируются по домену и собираются в приложении:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionResponse])
async def list_collections() -> list[CollectionResponse]:
    ...
```

```python
from app.collections.router import router as collections_router

app.include_router(collections_router, prefix="/api/v1")
```

Обратите внимание: префикс `/api/v1` задаётся один раз при подключении, а не дублируется в каждом
роутере.

### Зависимости — главный механизм FastAPI

Dependency injection здесь работает через аннотации параметров. Функция-зависимость объявляется
обычной функцией, а FastAPI вызывает её перед обработчиком и подставляет результат.

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/{collection_id}")
async def get_collection(collection_id: UUID, session: DbSession) -> CollectionResponse:
    ...
```

Разберём по частям:

* `Annotated[AsyncSession, Depends(get_db_session)]` — «тип `AsyncSession`, значение получить из
  `get_db_session`». Мы сохраняем это в псевдоним `DbSession`, чтобы не повторять конструкцию в каждом
  эндпоинте;
* зависимость с `yield` — это код до и после обработчика: всё до `yield` выполняется перед,
  всё после — гарантированно потом, даже при исключении. Так закрывается сессия БД;
* зависимости вкладываются друг в друга: `get_current_user` будет зависеть от `get_db_session`,
  и FastAPI разрулит порядок сам.

Такой же приём применим к аутентификации — на шаге 15 появится:

```python
CurrentUser = Annotated[User, Depends(get_current_user)]
```

и любой защищённый эндпоинт просто добавляет параметр `user: CurrentUser`.

### Где заканчивается ответственность роутера

Правило проекта жёсткое, и его стоит принять сразу: роутер делает только маршрутизацию, объявление
зависимостей, вызов сервиса и возврат схемы ответа. Никаких SQL-запросов, никакой бизнес-логики,
никаких вызовов внешних API. Сервисы, в свою очередь, не знают про HTTP и **не выбрасывают
`HTTPException`** — они выбрасывают доменные исключения, которые превращаются в HTTP-ответы
на границе (шаг 61).

```python
class VocabularyError(Exception):
    pass


class VocabularyItemNotFound(VocabularyError):
    def __init__(self, item_id: UUID) -> None:
        self.item_id = item_id
        super().__init__(f"Vocabulary item {item_id} not found")
```

Причина не в чистоте ради чистоты: ту же логику вызывает Celery-задача, где `HTTPException`
бессмысленен.

---

## 5. SQLAlchemy 2.x: модели и запросы

SQLAlchemy — ORM. В версии 2.x она использует аннотации типов, поэтому код выглядит почти как
Pydantic, но означает совсем другое: это описание таблиц.

### Базовый класс и модель

```python
from datetime import datetime
from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Lexeme(Base):
    __tablename__ = "lexemes"
    __table_args__ = (
        UniqueConstraint("language_id", "normalized_text", name="uq_lexemes_language_normalized"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id", ondelete="RESTRICT"))
    text: Mapped[str] = mapped_column(String(80))
    normalized_text: Mapped[str] = mapped_column(String(80), index=True)
    ipa: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    meanings: Mapped[list["Meaning"]] = relationship(back_populates="lexeme")
```

Ключевой момент, который экономит часы отладки: **`Mapped[str]` означает `NOT NULL`, а
`Mapped[str | None]` — nullable**. Аннотация напрямую управляет схемой БД. Если в модели написано
`Mapped[str]`, а в базе колонка допускает NULL, вы получите рассинхронизацию, которую заметите только
на реальных данных.

`relationship` — это не колонка, а навигация по связи. Она не создаёт поле в таблице.

### Запросы

Стиль 2.x — конструирование выражения и его выполнение:

```python
from sqlalchemy import select


async def find_by_normalized_text(
    session: AsyncSession, language_id: int, normalized_text: str
) -> Lexeme | None:
    statement = select(Lexeme).where(
        Lexeme.language_id == language_id,
        Lexeme.normalized_text == normalized_text,
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()
```

Методы получения результата, которые понадобятся:

| Метод | Возвращает | Когда |
| --- | --- | --- |
| `result.scalar_one_or_none()` | один объект или `None` | поиск по уникальному признаку |
| `result.scalar_one()` | один объект, иначе исключение | когда отсутствие — это баг |
| `result.scalars().all()` | список объектов | список |
| `result.all()` | список кортежей | когда в `select` несколько сущностей |

### Ленивая загрузка и почему она опасна в async

По умолчанию `relationship` загружается лениво: обращение к `lexeme.meanings` вызывает
дополнительный запрос. В асинхронном коде это приводит к исключению `MissingGreenlet`, потому что
неявный запрос нельзя выполнить без `await`.

Поэтому связи загружаются явно:

```python
from sqlalchemy.orm import selectinload

statement = (
    select(Lexeme)
    .where(Lexeme.id == lexeme_id)
    .options(selectinload(Lexeme.meanings).selectinload(Meaning.translations))
)
```

`selectinload` делает один дополнительный запрос на уровень связи — это и решает проблему N+1,
и держит код предсказуемым. Если увидели `MissingGreenlet` — вы забыли `options(...)`.

### Транзакции

Правило проекта: транзакцией владеет сервис, а не репозиторий. Репозиторий добавляет объекты
и делает `flush()`, когда нужен сгенерированный id, но `commit()` вызывает сервис — один раз,
в конце операции.

```python
async def create_vocabulary_item(self, session: AsyncSession, ...) -> UserVocabularyItem:
    item = UserVocabularyItem(...)
    session.add(item)
    await session.flush()
    return item
```

`flush()` отправляет SQL, но не завершает транзакцию — id уже доступен, откат ещё возможен.
`commit()` фиксирует. Наша зависимость `get_db_session` будет откатывать транзакцию при исключении,
поэтому частичных записей не останется.

---

## 6. Alembic: миграции

Alembic сравнивает модели SQLAlchemy с состоянием БД и генерирует файл миграции.

Рабочий цикл, который вы будете повторять много раз:

```bash
# 1. изменили или добавили модель
# 2. сгенерировали миграцию
uv run alembic revision --autogenerate -m "add lexemes table"

# 3. ОТКРЫЛИ сгенерированный файл и прочитали его
# 4. применили
uv run alembic upgrade head
```

Третий пункт не пропускается. Autogenerate — это помощник, а не источник истины: он регулярно не
замечает переименования (видит удаление + создание, то есть потерю данных), путается в изменениях
типов и не создаёт расширения PostgreSQL. Для нашего проекта, например, индекс `pg_trgm` придётся
дописать руками.

Полезные команды:

```bash
uv run alembic current           # какая ревизия применена
uv run alembic history           # цепочка ревизий
uv run alembic downgrade -1      # откатить одну
uv run alembic upgrade head      # применить все
```

Два правила, нарушение которых дорого стоит:

1. применённую миграцию **не редактируют** — создают новую;
2. каждая миграция должна иметь осмысленный `downgrade`, если откат в принципе возможен.

Готовые рецепты (расширения, enum-типы, наполнение данными) — в
[07-database-reference.md](07-database-reference.md).

---

## 7. Celery: фоновые задачи

Celery выполняет код вне цикла запрос-ответ. Наш случай: после выбора значения пользователь не должен
ждать обращений к словарю, аудио и AI — карточка создаётся сразу со статусом `PENDING`, а наполнение
идёт в фоне.

Устройство:

* **broker** (Redis, БД 1) — очередь, куда API кладёт сообщение о задаче;
* **worker** — отдельный процесс, который берёт сообщения и выполняет;
* **result backend** (Redis, БД 2) — где лежат результаты.

Объявление задачи:

```python
from app.common.celery_app import celery_app


@celery_app.task(
    name="enrichment.enrich_vocabulary_item",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def enrich_vocabulary_item(self, vocabulary_item_id: str) -> None:
    ...
```

Постановка из API:

```python
enrich_vocabulary_item.delay(str(item.id))
```

Запуск worker:

```bash
uv run celery -A app.common.celery_app:celery_app worker --loglevel=info --concurrency=2
```

### Три правила, специфичные для нашего проекта

**Аргументы задачи — только простые сериализуемые значения.** Передаётся `str(uuid)`, а не
ORM-объект. ORM-объект привязан к сессии, которой в worker нет, и он не сериализуется в JSON.

**Задача синхронная, а наш код асинхронный.** Мост — `asyncio.run`:

```python
import asyncio


@celery_app.task(name="enrichment.enrich_vocabulary_item", bind=True, max_retries=3)
def enrich_vocabulary_item(self, vocabulary_item_id: str) -> None:
    asyncio.run(run_enrichment(UUID(vocabulary_item_id)))
```

`asyncio.run` создаёт свой event loop и закрывает его. Отсюда важное следствие: сессия БД и
HTTP-клиент создаются **внутри** корутины, а не на уровне модуля. Объект, созданный в одном loop,
нельзя использовать в другом — это даёт трудноуловимые зависания.

**Задача должна быть идемпотентной.** Celery может выполнить сообщение дважды (перезапуск worker,
повторная доставка). Для enrichment это значит: перед генерацией проверяем, нет ли уже готового
`MeaningContent`, и держим Redis-лок на время генерации. Детали — шаг 38.

Ретраи ограничены и с возрастающей задержкой:

```python
try:
    ...
except ProviderTemporaryError as error:
    raise self.retry(exc=error, countdown=2 ** self.request.retries * 10)
```

Бесконечных ретраев быть не должно: провайдер, который лежит, будет лежать и на сотой попытке,
а карточка должна перейти в `PARTIAL` или `FAILED` и остаться пригодной к использованию.

---

## 8. Структура backend-модуля

Модуль соответствует домену. Файлы создаются **только те, для которых есть содержание** — пустых
слоёв не бывает.

```text
app/
├── main.py                 сборка FastAPI, подключение роутеров
├── common/
│   ├── settings.py         Settings на pydantic-settings
│   ├── database.py         engine, session factory, зависимость сессии
│   ├── celery_app.py       объект Celery
│   ├── logging.py          структурное логирование
│   ├── errors.py           базовые доменные исключения и обработчики
│   └── rate_limit.py       ограничение частоты запросов
├── auth/
│   ├── router.py           POST /auth/telegram
│   ├── schemas.py          TelegramAuthRequest, AuthTokenResponse
│   ├── telegram.py         проверка подписи initData
│   ├── tokens.py           выпуск и разбор JWT
│   ├── dependencies.py     get_current_user
│   └── service.py          поиск или создание User + AuthIdentity
├── users/
├── languages/
├── lexicon/
│   ├── models.py           Lexeme, Meaning, Translation, MeaningContent
│   ├── normalization.py    приведение текста к нормальной форме
│   ├── repository.py
│   ├── lookup_service.py
│   ├── schemas.py
│   └── router.py
├── vocabulary/
├── collections/
├── study/
├── enrichment/
│   ├── service.py          сам pipeline, вызывается и из задачи, и из тестов
│   └── tasks.py            тонкая Celery-обёртка
├── integrations/
│   ├── dictionary/
│   │   ├── provider.py     протокол + DTO
│   │   ├── yandex.py
│   │   └── wiktionary.py
│   ├── ai/
│   │   ├── provider.py
│   │   └── openai_provider.py
│   └── audio/
│       ├── provider.py
│       └── wikimedia.py
└── analytics/
```

Соответствие «что куда кладём»:

| Что вы пишете | Куда |
| --- | --- |
| Определение таблицы | `<модуль>/models.py` |
| Схема запроса/ответа API | `<модуль>/schemas.py` |
| Обработчик HTTP | `<модуль>/router.py` |
| Бизнес-правило, workflow | `<модуль>/service.py` |
| SQL-запрос | `<модуль>/repository.py` |
| Вызов внешнего API | `integrations/<тип>/<провайдер>.py` |
| Чистое преобразование данных | отдельный модуль с доменным именем |

---

## 9. Протоколы вместо интерфейсов

Для провайдеров нужен контракт: «любая реализация словаря умеет искать значения». В Python это
`Protocol` — структурная типизация, аналог интерфейсов TypeScript. Наследование не требуется,
достаточно совпадения сигнатур.

```python
from typing import Protocol


class DictionaryProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def lookup(self, request: DictionaryLookupRequest) -> DictionaryLookupResult: ...
```

Сервис зависит от протокола, а не от конкретного класса:

```python
class LexemeLookupService:
    def __init__(
        self,
        primary_provider: DictionaryProvider,
        fallback_provider: DictionaryProvider,
        ai_provider: AIProvider,
    ) -> None:
        self._primary_provider = primary_provider
        self._fallback_provider = fallback_provider
        self._ai_provider = ai_provider
```

Практическая выгода: в тестах подставляется класс на десять строк, возвращающий фиксированный ответ,
и тесты не ходят в интернет. Это прямое требование раздела 36 правил проекта.

Подчёркивание в именах: `_primary_provider` означает «внутреннее, не трогать снаружи». Python это не
запрещает технически, но соглашение соблюдается повсеместно.

---

## 10. Инструменты качества

```bash
uv run ruff check app tests        # линтер
uv run ruff format app tests       # форматирование
uv run mypy app                    # проверка типов
uv run pytest                      # тесты
uv run pytest -k normalization -v  # только подходящие по имени
```

`ruff` заменяет flake8, isort и black одной быстрой командой. Настройки — в `pyproject.toml`
(шаг 7). Эти же команды пойдут в CI на шаге 24, так что держите их зелёными локально.

---

## Что читать дальше

* Шаги недели 1 — [03-week1-foundation.md](03-week1-foundation.md)
* Все таблицы и рецепты Alembic — [07-database-reference.md](07-database-reference.md)
* Провайдеры словаря, AI и аудио — [09-integrations-reference.md](09-integrations-reference.md)
* Официальная документация, когда нужно глубже: [FastAPI](https://fastapi.tiangolo.com),
  [SQLAlchemy 2.0 ORM](https://docs.sqlalchemy.org/en/20/orm/quickstart.html),
  [Pydantic](https://docs.pydantic.dev/latest/),
  [Celery](https://docs.celeryq.dev/en/stable/)
