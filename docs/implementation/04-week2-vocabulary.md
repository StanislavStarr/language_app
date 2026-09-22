# Неделя 2 — Vocabulary (шаги 25–42)

## Цель недели

К концу недели работает главный продуктовый сценарий: пользователь создаёт тему, вводит слово,
получает до трёх значений, выбирает Meaning, сохраняет карточку, дожидается enrichment и открывает
готовую карточку с переводом, IPA, аудио, definition и example.

Ориентировочное время: 30 часов.

Перед началом:

* [01-primer-python-backend.md](01-primer-python-backend.md) — разделы 5–9 (модели, репозитории,
  протоколы, Celery);
* [02-primer-angular.md](02-primer-angular.md) — разделы 3–7 (signals, `inject()`, HTTP, роутинг,
  формы);
* [07-database-reference.md](07-database-reference.md) — полные таблицы, индексы, рецепты Alembic;
* [08-api-reference.md](08-api-reference.md) — точные JSON-контракты всех эндпоинтов этой недели;
* [09-integrations-reference.md](09-integrations-reference.md) — словари, аудио, OpenAI. Шаги 29–33
  и 38 **не копируют** реализации провайдеров: они живут в 09.

Неделя 1 уже дала: `CurrentUser`, JWT, onboarding, PostgreSQL, Redis, Celery worker, `pg_trgm`,
`ffmpeg` в образе backend, заглушку главного экрана. Не пересоздавайте это.

---

## Карта модулей этой недели

```text
backend/app/
├── lexicon/
│   ├── models.py              Lexeme, Meaning, Translation, MeaningContent
│   ├── normalization.py
│   ├── repository.py
│   ├── lookup_service.py
│   ├── schemas.py
│   └── router.py
├── vocabulary/
│   ├── models.py              UserVocabularyItem
│   ├── repository.py
│   ├── service.py
│   ├── schemas.py
│   └── router.py
├── collections/
│   ├── models.py              Collection, CollectionItem
│   ├── repository.py
│   ├── service.py
│   ├── schemas.py
│   └── router.py
├── enrichment/
│   ├── service.py
│   ├── locks.py
│   └── tasks.py               замена count_users на настоящую задачу
└── integrations/              протоколы и реализации — шаги 29–33, детали в 09

frontend/src/app/features/
├── collections/               главный экран и CRUD тем
└── vocabulary/                lookup, выбор Meaning, карточка, аудио
```

Имена сущностей фиксированы продуктовым планом: **Lexeme**, **Meaning**, **Translation**,
**MeaningContent**, **UserVocabularyItem**, **Collection**. Не заменяйте их на Word/Card/Theme.

«Все слова» — **не** Collection. Это системное представление личного словаря. Неправильные глаголы
появятся на неделе 3 — на главном экране оставьте карточку-заглушку.

---

## Шаг 25. Модели лексикона и миграция с `pg_trgm`

### Цель

В PostgreSQL есть общие таблицы `lexemes`, `meanings`, `translations`, `meaning_contents` и GIN-индекс
для нечёткого поиска опечаток.

Расширение `pg_trgm` уже включено миграцией шага 11. Здесь его **не** создаём повторно — добавляем
индекс `gin_trgm_ops` на `lexemes.normalized_text`. Autogenerate этот индекс обычно не пишет,
его дописывают руками. Рецепт — в [07-database-reference.md](07-database-reference.md).

Идентификаторы: **bigint** для лексикона (шарятся между всеми пользователями), **UUID** — только
для пользовательских сущностей на шаге 26.

### Файлы

`backend/app/lexicon/models.py`, правка `backend/app/common/models_registry.py`,
новая Alembic-миграция.

### Действия

```bash
mkdir -p backend/app/lexicon
touch backend/app/lexicon/__init__.py
```

Создайте `backend/app/lexicon/models.py`:

```python
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.database import Base
from app.common.mixins import TimestampMixin
from app.users.models import CefrLevel


class LexemeType(StrEnum):
    WORD = "word"
    PHRASE = "phrase"


class LexicalSource(StrEnum):
    YANDEX = "yandex"
    WIKTIONARY = "wiktionary"
    AI = "ai"
    WIKIMEDIA = "wikimedia"


class MeaningContentStatus(StrEnum):
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"


class Lexeme(Base, TimestampMixin):
    __tablename__ = "lexemes"
    __table_args__ = (
        UniqueConstraint("language_id", "normalized_text", name="uq_lexemes_language_normalized"),
        Index(
            "ix_lexemes_normalized_text_trgm",
            "normalized_text",
            postgresql_using="gin",
            postgresql_ops={"normalized_text": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    language_id: Mapped[int] = mapped_column(
        ForeignKey("languages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(80), nullable=False)
    type: Mapped[LexemeType] = mapped_column(
        SqlEnum(LexemeType, name="lexeme_type", native_enum=True), nullable=False
    )
    ipa: Mapped[str | None] = mapped_column(String(120))
    audio_url: Mapped[str | None] = mapped_column(String(512))
    audio_source: Mapped[LexicalSource | None] = mapped_column(
        SqlEnum(LexicalSource, name="lexical_source", native_enum=True)
    )

    meanings: Mapped[list["Meaning"]] = relationship(back_populates="lexeme")


class Meaning(Base):
    __tablename__ = "meanings"

    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(
        ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_of_speech: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[LexicalSource] = mapped_column(
        SqlEnum(LexicalSource, name="lexical_source", native_enum=True, create_type=False),
        nullable=False,
    )
    source_external_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lexeme: Mapped[Lexeme] = relationship(back_populates="meanings")
    translations: Mapped[list["Translation"]] = relationship(back_populates="meaning")
    contents: Mapped[list["MeaningContent"]] = relationship(back_populates="meaning")


class Translation(Base):
    __tablename__ = "translations"

    id: Mapped[int] = mapped_column(primary_key=True)
    meaning_id: Mapped[int] = mapped_column(
        ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    language_id: Mapped[int] = mapped_column(
        ForeignKey("languages.id", ondelete="RESTRICT"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[LexicalSource] = mapped_column(
        SqlEnum(LexicalSource, name="lexical_source", native_enum=True, create_type=False),
        nullable=False,
    )

    meaning: Mapped[Meaning] = relationship(back_populates="translations")


class MeaningContent(Base):
    __tablename__ = "meaning_contents"
    __table_args__ = (
        UniqueConstraint(
            "meaning_id",
            "cefr_level",
            "prompt_version",
            name="uq_meaning_contents_meaning_cefr_prompt",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meaning_id: Mapped[int] = mapped_column(
        ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cefr_level: Mapped[CefrLevel] = mapped_column(
        SqlEnum(CefrLevel, name="cefr_level", native_enum=True, create_type=False),
        nullable=False,
    )
    definition: Mapped[str | None] = mapped_column(Text)
    example: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[MeaningContentStatus] = mapped_column(
        SqlEnum(MeaningContentStatus, name="meaning_content_status", native_enum=True),
        nullable=False,
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    meaning: Mapped[Meaning] = relationship(back_populates="contents")
```

Несколько решений, которые нельзя «упростить»:

* `create_type=False` на повторном использовании enum (`lexical_source`, `cefr_level`) — иначе Alembic
  попытается создать тип второй раз и миграция упадёт;
* уникальность `language_id + normalized_text` защищает от двух Lexeme для `Clarify` и `clarify`;
* уникальность `meaning_id + cefr_level + prompt_version` — защита от двойной AI-генерации. Redis-лок
  на шаге 38 — вторая линия, ограничение в БД — настоящая;
* `source_context` **сюда не кладём**: это персональные данные UserVocabularyItem, общий кэш
  MeaningContent их не должен знать;
* IPA и audio живут на Lexeme: одно произношение на учебную единицу, не на каждое значение.

`Mapped[str]` = `NOT NULL`, `Mapped[str | None]` = nullable. Это не «для удобства», это схема БД.

Обновите `backend/app/common/models_registry.py` — добавьте импорты `Lexeme`, `Meaning`,
`Translation`, `MeaningContent`. Без импорта Alembic «не увидит» таблицы и в следующей миграции
предложит их удалить.

Сгенерируйте миграцию:

```bash
cd backend
POSTGRES_HOST=localhost uv run alembic revision --autogenerate -m "add lexicon tables"
```

Откройте файл и проверьте:

* четыре таблицы и enum-типы `lexeme_type`, `lexical_source`, `meaning_content_status`;
* `cefr_level` **не** создаётся заново;
* есть `uq_lexemes_language_normalized` и `uq_meaning_contents_meaning_cefr_prompt`;
* есть GIN-индекс. Если autogenerate его пропустил, допишите в `upgrade()` / `downgrade()`:

```python
def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lexemes_normalized_text_trgm "
        "ON lexemes USING gin (normalized_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_lexemes_normalized_text_trgm")
    op.execute("DROP TYPE IF EXISTS meaning_content_status")
    op.execute("DROP TYPE IF EXISTS lexical_source")
    op.execute("DROP TYPE IF EXISTS lexeme_type")
```

Порядок в `downgrade()`: сначала таблицы и индекс, потом типы. Иначе PostgreSQL откажется удалить
enum, на который ещё ссылаются колонки.

```bash
POSTGRES_HOST=localhost uv run alembic upgrade head
POSTGRES_HOST=localhost uv run alembic downgrade -1
POSTGRES_HOST=localhost uv run alembic upgrade head
```

### Проверка

```bash
cd infra
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\d lexemes"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\d meaning_contents"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "
select indexname, indexdef from pg_indexes
where tablename = 'lexemes' and indexname like '%trgm%';
"
```

У `lexemes` должен быть уникальный constraint на пару язык+нормализованный текст и GIN-индекс
с `gin_trgm_ops`. У `meaning_contents` — unique на тройку meaning/cefr/prompt.

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "SELECT similarity('clarify', 'clarfy');"
```

Число больше нуля означает, что `pg_trgm` работает. Если ошибка `function similarity does not exist` —
расширение из шага 11 не применено, см. [11-troubleshooting.md](11-troubleshooting.md).

### Коммит

`feat(backend): add lexicon models and trigram index`

---

## Шаг 26. Модели личного словаря и тем

### Цель

Появились персональные таблицы `user_vocabulary_items`, `collections`, `collection_items`.

Правило из продуктового плана: одна учебная единица может быть сразу в нескольких темах.
«Все слова» в БД **не создаём** — это `GET /api/v1/vocabulary` без фильтра по коллекции.

### Файлы

`backend/app/vocabulary/models.py`, `backend/app/collections/models.py`,
правка `models_registry.py`, новая миграция.

### Действия

```bash
mkdir -p backend/app/vocabulary backend/app/collections
touch backend/app/vocabulary/__init__.py backend/app/collections/__init__.py
```

`backend/app/vocabulary/models.py`:

```python
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.database import Base
from app.common.mixins import TimestampMixin


class EnrichmentStatus(StrEnum):
    PENDING = "PENDING"
    ENRICHING = "ENRICHING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class UserVocabularyItem(Base, TimestampMixin):
    __tablename__ = "user_vocabulary_items"
    __table_args__ = (
        UniqueConstraint("user_id", "meaning_id", name="uq_user_vocabulary_items_user_meaning"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meaning_id: Mapped[int] = mapped_column(
        ForeignKey("meanings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_context: Mapped[str | None] = mapped_column(Text)
    personal_note: Mapped[str | None] = mapped_column(Text)
    study_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_studied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrichment_status: Mapped[EnrichmentStatus] = mapped_column(
        SqlEnum(EnrichmentStatus, name="enrichment_status", native_enum=True),
        nullable=False,
        default=EnrichmentStatus.PENDING,
    )

    collection_links: Mapped[list["CollectionItem"]] = relationship(
        back_populates="vocabulary_item"
    )
```

`user_id + meaning_id` уникальны: повторный выбор того же значения не создаёт вторую карточку,
а добавляет существующую в новые темы (шаг 37). `source_context` и `personal_note` — только здесь,
не в Lexeme и не в MeaningContent.

`ondelete="RESTRICT"` на `meaning_id`: удаление пользователя не должно каскадом сносить общий лексикон.
Наоборот, удаление UserVocabularyItem не трогает Meaning.

`backend/app/collections/models.py`:

```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.database import Base
from app.common.mixins import TimestampMixin
from app.vocabulary.models import UserVocabularyItem


class Collection(Base, TimestampMixin):
    __tablename__ = "collections"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(240))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    items: Mapped[list["CollectionItem"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "user_vocabulary_item_id",
            name="uq_collection_items_collection_item",
        ),
    )

    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    user_vocabulary_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_vocabulary_items.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    collection: Mapped[Collection] = relationship(back_populates="items")
    vocabulary_item: Mapped[UserVocabularyItem] = relationship(back_populates="collection_links")
```

`user_id` nullable заранее: системная тема неправильных глаголов на неделе 3 будет с `is_system=True`
и без владельца. Пользовательские темы этой недели всегда имеют `user_id` и `is_system=False`.

Удаление темы снимает только связи `collection_items`. Карточки остаются в «Всех словах».
Удаление карточки из словаря каскадом снимает её из всех тем.

Импортируйте модели в `models_registry.py`.

```bash
cd backend
POSTGRES_HOST=localhost uv run alembic revision --autogenerate -m "add vocabulary and collections"
```

В сгенерированном файле проверьте unique `uq_user_vocabulary_items_user_meaning`, составной PK
`collection_items`, enum `enrichment_status` и `DROP TYPE` в `downgrade()`. Примените и откатитесь
на одну ревизию, затем снова `upgrade head`.

### Проверка

```bash
cd infra
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\d user_vocabulary_items"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\d collections"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\d collection_items"
```

В `user_vocabulary_items` должны быть UUID `id`, unique на `(user_id, meaning_id)`, колонки
`source_context`, `personal_note`, `enrichment_status`. В `collections` — nullable `user_id` и
`is_system`.

### Коммит

`feat(backend): add vocabulary item and collection models`

---

## Шаг 27. Нормализация текста с тестами

### Цель

Одинаковый ввод (`Clarify`, ` clarify  `, `CLARIFY`) сводится к одному ключу поиска. Лемматизации нет:
`run` и `running` — разные Lexeme.

Это чистая функция без БД и HTTP. Её вызывают lookup, репозиторий и проверка лимита длины.
Реализацию не размазывайте по сервисам.

### Файлы

`backend/app/lexicon/normalization.py`, `backend/tests/test_normalization.py`.

### Действия

`backend/app/lexicon/normalization.py`:

```python
import re
from enum import StrEnum

from app.lexicon.models import LexemeType

_WHITESPACE = re.compile(r"\s+")
_MAX_TEXT_LENGTH = 80
_MAX_PHRASE_WORDS = 5


class NormalizationError(ValueError):
    pass


def normalize_lexeme_text(text: str) -> str:
    collapsed = _WHITESPACE.sub(" ", text.strip()).lower()
    if not collapsed:
        raise NormalizationError("text is empty")
    if len(collapsed) > _MAX_TEXT_LENGTH:
        raise NormalizationError("text is longer than 80 characters")
    word_count = len(collapsed.split(" "))
    if word_count > _MAX_PHRASE_WORDS:
        raise NormalizationError("phrase cannot contain more than 5 words")
    return collapsed


def detect_lexeme_type(normalized_text: str) -> LexemeType:
    if " " in normalized_text:
        return LexemeType.PHRASE
    return LexemeType.WORD
```

Правила совпадают с продуктовым планом: регистр, trim, схлопывание пробелов. Без стемминга,
без «s» на конце, без приведения `running` → `run`. Лимит 5 слов и 80 символов — тоже из плана,
проверяем на нормализованной строке, чтобы `"  look   forward  to  "` не обошёл лимит за счёт пробелов.

`backend/tests/test_normalization.py`:

```python
import pytest

from app.lexicon.models import LexemeType
from app.lexicon.normalization import (
    NormalizationError,
    detect_lexeme_type,
    normalize_lexeme_text,
)


def test_clarify_equals_clarify() -> None:
    assert normalize_lexeme_text("Clarify") == "clarify"
    assert normalize_lexeme_text("CLARIFY") == "clarify"
    assert normalize_lexeme_text("  clarify  ") == "clarify"


def test_phrase_spaces_are_collapsed() -> None:
    assert normalize_lexeme_text("Look   forward\tto") == "look forward to"
    assert detect_lexeme_type("look forward to") is LexemeType.PHRASE


def test_run_is_not_running() -> None:
    assert normalize_lexeme_text("run") != normalize_lexeme_text("running")
    assert normalize_lexeme_text("ran") != normalize_lexeme_text("run")


def test_empty_and_too_long_are_rejected() -> None:
    with pytest.raises(NormalizationError):
        normalize_lexeme_text("   ")
    with pytest.raises(NormalizationError):
        normalize_lexeme_text("x" * 81)


def test_phrase_longer_than_five_words_is_rejected() -> None:
    with pytest.raises(NormalizationError):
        normalize_lexeme_text("one two three four five six")


def test_single_word_is_word_type() -> None:
    assert detect_lexeme_type("clarify") is LexemeType.WORD
```

### Проверка

```bash
cd backend
uv run pytest tests/test_normalization.py -v
```

Шесть тестов зелёные. Если `test_run_is_not_running` красный — в нормализацию случайно попал стеммер;
уберите его, лемматизация в MVP запрещена.

### Коммит

`feat(backend): add lexeme text normalization`

---

## Шаг 28. Репозитории лексикона

### Цель

Поиск, сохранение значений и подсказка по опечатке живут в репозитории, а не в сервисе lookup и не
в роутере. Сервис решает «что делать», репозиторий — «как прочитать/записать».

Про `selectinload` в async: обращение к `lexeme.meanings` без явной загрузки даёт `MissingGreenlet`.
Связи грузим в том же запросе. См. [01-primer-python-backend.md](01-primer-python-backend.md),
раздел 5.

### Файлы

`backend/app/lexicon/repository.py`, `backend/tests/test_lexicon_repository.py`.

### Действия

`backend/app/lexicon/repository.py`:

```python
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.lexicon.models import Lexeme, LexicalSource, Meaning, Translation
from app.lexicon.normalization import detect_lexeme_type

TYPO_SIMILARITY_THRESHOLD = 0.45


class LexiconRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _lexeme_with_meanings(self) -> Select[tuple[Lexeme]]:
        return select(Lexeme).options(
            selectinload(Lexeme.meanings).selectinload(Meaning.translations)
        )

    async def find_by_normalized_text(
        self, language_id: int, normalized_text: str
    ) -> Lexeme | None:
        statement = self._lexeme_with_meanings().where(
            Lexeme.language_id == language_id,
            Lexeme.normalized_text == normalized_text,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def suggest_by_trigram(
        self, language_id: int, normalized_text: str
    ) -> str | None:
        similarity = func.similarity(Lexeme.normalized_text, normalized_text)
        statement = (
            select(Lexeme.normalized_text)
            .where(
                Lexeme.language_id == language_id,
                Lexeme.normalized_text != normalized_text,
                similarity >= TYPO_SIMILARITY_THRESHOLD,
            )
            .order_by(similarity.desc())
            .limit(1)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_or_create_lexeme(
        self,
        *,
        language_id: int,
        text: str,
        normalized_text: str,
        ipa: str | None,
    ) -> Lexeme:
        existing = await self.find_by_normalized_text(language_id, normalized_text)
        if existing is not None:
            if ipa and existing.ipa is None:
                existing.ipa = ipa
            return existing

        lexeme = Lexeme(
            language_id=language_id,
            text=text,
            normalized_text=normalized_text,
            type=detect_lexeme_type(normalized_text),
            ipa=ipa,
        )
        self._session.add(lexeme)
        await self._session.flush()
        return lexeme

    async def add_meaning(
        self,
        lexeme: Lexeme,
        *,
        part_of_speech: str,
        source: LexicalSource,
        source_external_id: str | None,
        translations: list[tuple[int, str]],
    ) -> Meaning:
        for existing in lexeme.meanings:
            same_pos = existing.part_of_speech == part_of_speech
            existing_texts = {item.text for item in existing.translations}
            incoming_texts = {text for _, text in translations}
            if same_pos and existing_texts & incoming_texts:
                return existing

        meaning = Meaning(
            lexeme_id=lexeme.id,
            part_of_speech=part_of_speech,
            source=source,
            source_external_id=source_external_id,
        )
        self._session.add(meaning)
        await self._session.flush()
        for language_id, text in translations:
            self._session.add(
                Translation(
                    meaning_id=meaning.id,
                    language_id=language_id,
                    text=text,
                    source=source,
                )
            )
        await self._session.flush()
        await self._session.refresh(lexeme, attribute_names=["meanings"])
        return meaning
```

`flush`, не `commit`: транзакцией владеет сервис lookup. Репозиторий не принимает бизнес-решений
«вызывать ли Яндекс» и не возвращает HTTP.

Порог `0.45` отсекает далёкие совпадения (`cat` не предлагает `clarify`). Подсказка ищется только
среди уже сохранённых Lexeme — для пустой базы её не будет, и это нормально.

Тест репозитория поднимает тестовую БД так же, как тесты шага 14 не требуют Telegram. Используйте
фикстуру сессии из [10-testing-reference.md](10-testing-reference.md), когда она появится; пока
достаточно вставить две строки и вызвать `suggest_by_trigram("clarfy")`.

Минимальный тест без фикстур инфраструктуры — проверьте хотя бы, что порог и запрос собираются:
интеграционный тест с Postgres добавите, когда дойдёте до шага 34. На этом шаге обязателен хотя бы
один тест `find_by_normalized_text` против реальной БД (CI уже поднимает Postgres).

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.lexicon.models import Lexeme, LexemeType
from app.lexicon.repository import LexiconRepository


@pytest.mark.asyncio
async def test_find_by_normalized_text_returns_saved_lexeme(
    db_session: AsyncSession, english_language_id: int
) -> None:
    db_session.add(
        Lexeme(
            language_id=english_language_id,
            text="Clarify",
            normalized_text="clarify",
            type=LexemeType.WORD,
        )
    )
    await db_session.commit()

    found = await LexiconRepository(db_session).find_by_normalized_text(
        english_language_id, "clarify"
    )
    assert found is not None
    assert found.text == "Clarify"


@pytest.mark.asyncio
async def test_trigram_suggests_clarify_for_clarfy(
    db_session: AsyncSession, english_language_id: int
) -> None:
    db_session.add(
        Lexeme(
            language_id=english_language_id,
            text="clarify",
            normalized_text="clarify",
            type=LexemeType.WORD,
        )
    )
    await db_session.commit()

    suggestion = await LexiconRepository(db_session).suggest_by_trigram(
        english_language_id, "clarfy"
    )
    assert suggestion == "clarify"
```

Фикстуры `db_session` и `english_language_id` возьмите из существующих тестов языков / из 10-го
справочника. Если фикстуры ещё нет — создайте `backend/tests/conftest.py` с async-движком на
`POSTGRES_*` из окружения CI (шаг 24 уже задаёт тестовую БД).

### Проверка

```bash
cd backend
uv run pytest tests/test_lexicon_repository.py -v
uv run ruff check app/lexicon
```

`clarfy` предлагает `clarify`. Точное совпадение `clarify` не должно возвращать подсказку на само себя.

### Коммит

`feat(backend): add lexicon repository with trigram suggestions`

---

## Шаг 29. Протокол `DictionaryProvider` и нормализованные DTO

### Цель

Сервис lookup зависит от протокола, а не от Яндекса. Форматы внешних ответов остаются внутри
`app/integrations/` и наружу не выходят.

### Файлы

`backend/app/integrations/dictionary/provider.py`,
`backend/app/integrations/errors.py`,
`backend/app/integrations/http_client.py`.

### Действия

Не изобретайте второй набор DTO. Скопируйте и реализуйте **раздел 2** справочника
[09-integrations-reference.md](09-integrations-reference.md): `PartOfSpeech`, `DictionaryTranslation`,
`DictionaryMeaning`, `DictionaryEntry`, `DictionaryLookupResult`, протокол `DictionaryProvider`.

Там же — `ProviderError` / `ProviderTemporaryError` / `ProviderPermanentError` и общий
`ProviderHttpClient` из **раздела 3** (таймаут, ретраи на 429/5xx, логирование без секретов).

Контракт, который должен получиться:

```python
class DictionaryProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def lookup(self, text: str) -> DictionaryLookupResult: ...
```

`LexemeLookupService` на шаге 34 принимает `DictionaryProvider`, а не `YandexDictionaryProvider`.
В тестах подставляется объект на десять строк. Это требование раздела 36 правил проекта.

`frozen=True, slots=True` на dataclass оставляйте: результат внешнего запроса не должен мутировать
по пути через слои.

### Проверка

```bash
cd backend
uv run mypy app/integrations
```

Протокол должен импортироваться без реализации Яндекса. Если `lookup_service.py` уже тянет
`yandex.py` — зависимость направлена не туда, поправьте до шага 34.

### Коммит

`feat(backend): add dictionary provider protocol and http client`

---

## Шаг 30. Реализация Yandex Dictionary

### Цель

Основной словарь отвечает переводом, частью речи и транскрипцией. Ключ — `YANDEX_DICTIONARY_API_KEY`
из `.env` шага 6.

### Файлы

`backend/app/integrations/dictionary/yandex.py`.

### Действия

Полная реализация, разбор JSON, таблица `POS_MAPPING` и обработка ошибок — **раздел 4**
[09-integrations-reference.md](09-integrations-reference.md). Здесь только то, что нельзя упустить.

Запрос: `GET https://dictionary.yandex.net/api/v1/dicservice.json/lookup` с `lang=en-ru`, `flags=4`,
таймаут `yandex_dictionary_timeout_seconds` (по умолчанию 5 с, уже есть в `Settings`).

Маппинг полей:

| Поле Яндекса | Куда |
| --- | --- |
| `def[].ts` | `DictionaryEntry.ipa` |
| `def[].pos` | `PartOfSpeech` через `POS_MAPPING` |
| `def[].tr[]` | **одно Meaning на один `tr`**, не на один `def` |
| `def[].tr[].text` | `DictionaryTranslation.text` |
| `def[].tr[].mean[]` | подсказка смысла (`берег (shore)`) |
| `def[].tr[].syn[]` | синонимы перевода |

«Банк» и «берег» — разные Meaning. Если схлопнуть их в одно «существительное», пользователю нечего
выбирать.

Неверный ключ и 400 — `ProviderPermanentError`, ретраить бессмысленно. Таймаут и 503 —
`ProviderTemporaryError`.

Не коммитьте ключ. Он уже в `.env`, файл в `.gitignore` с недели 1.

### Проверка

```bash
cd backend
uv run python -c "
import asyncio
from app.common.settings import get_settings
from app.integrations.dictionary.yandex import YandexDictionaryProvider

async def main() -> None:
    settings = get_settings()
    provider = YandexDictionaryProvider(
        api_key=settings.yandex_dictionary_api_key,
        timeout_seconds=settings.yandex_dictionary_timeout_seconds,
        user_agent=settings.wikimedia_user_agent,
    )
    result = await provider.lookup('bank')
    print(result.provider_name, len(result.entries), result.entries[0].ipa if result.entries else None)

asyncio.run(main())
"
```

Ожидается несколько значений и IPA вроде `bæŋk`. Пустой ответ на `bank` — проверьте ключ и `lang=en-ru`.

Юнит-тесты пишите на сохранённом JSON из раздела 4 справочника 09, без сети.

### Коммит

`feat(backend): add yandex dictionary provider`

---

## Шаг 31. Реализация Wiktionary

### Цель

Fallback-словарь добирает английские определения, когда у Яндекса их нет. Ключ не нужен.

### Файлы

`backend/app/integrations/dictionary/wiktionary.py`.

### Действия

Реализация — **раздел 5** [09-integrations-reference.md](09-integrations-reference.md).

Обязательный заголовок `User-Agent` с контактом: Wikimedia отклоняет анонимные запросы. Значение
берите из `Settings.wikimedia_user_agent`. Без него шаг «работает у вас» и падает в Docker.

Три ловушки ответа:

1. нужен ключ `en`, остальные языки игнорировать;
2. definitions приходят с HTML — вычистить теги, иначе они попадут в карточку и на этап «написание
   по definition»;
3. пустые первые определения пропускать.

Правило вызова из продуктового плана: второй провайдер вызывается **только если первого не хватило**
(нет IPA, перевода или определения). Это решение lookup-сервиса на шаге 34, не самого Wiktionary.

Таймаут — `wiktionary_timeout_seconds`.

### Проверка

```bash
curl -s -H "User-Agent: english-vocabulary-app/0.1 (contact: you@example.com)" \
  "https://en.wiktionary.org/api/rest_v1/page/definition/bank" | python3 -m json.tool | head
```

Заголовок обязателен и в `curl`, и в провайдере. Затем вызовите `WiktionaryProvider.lookup("bank")`
из Python — в DTO не должно остаться `<a href=`.

### Коммит

`feat(backend): add wiktionary dictionary provider`

---

## Шаг 32. `AudioProvider` и конвертация ogg → mp3

### Цель

Произношение скачивается с Wikimedia Commons, конвертируется в mp3 и кладётся в том, который Nginx
раздаёт с `/media/`. Safari и WKWebView на iOS **не играют ogg**; Telegram на iPhone использует
WKWebView. Ссылка на ogg «работает» на Android и молча мёртвая на iPhone.

`ffmpeg` уже установлен в `backend/Dockerfile` на шаге 9 и локально на шаге 1.

### Файлы

`backend/app/integrations/audio/provider.py`,
`backend/app/integrations/audio/wikimedia.py`,
`backend/app/integrations/audio/storage.py`.

### Действия

Протокол, поиск `File:En-us-{word}.ogg`, скачивание, вызов `ffmpeg` и сохранение —
**раздел 6** [09-integrations-reference.md](09-integrations-reference.md).

Коротко, что должно получиться:

```python
class AudioProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def find_pronunciation(self, text: str) -> AudioCandidate | None: ...
```

`PronunciationAudioStorage` скачивает ogg, гоняет через `ffmpeg` в mp3, возвращает публичный URL вида
`http://localhost:8080/media/audio/en-us-bank.mp3`. Конвертация — блокирующая: она живёт в Celery
(шаг 38), не в FastAPI-запросе. Таймаут `ffmpeg` обязателен, иначе повреждённый файл подвесит worker.

User-Agent снова обязателен. Для фраз аудио в MVP можно не искать: Commons хранит в основном одиночные
слова. Отсутствие файла → `None`, карточка станет `PARTIAL`, а не `FAILED`.

### Проверка

```bash
cd infra
docker compose exec celery-worker ffmpeg -version | head -1
```

Локально, без Celery:

```bash
ffmpeg -y -i /tmp/sample.ogg -codec:a libmp3lame -qscale:a 4 /tmp/sample.mp3
```

Если `ffmpeg` не найден в контейнере — пересоберите образ backend (worker берёт тот же Dockerfile).

### Коммит

`feat(backend): add wikimedia audio provider with mp3 conversion`

---

## Шаг 33. Протокол `AIProvider` и OpenAI Responses API

### Цель

AI генерирует definition + example и, если словари пустые, fallback-значения. AI **не** источник
истины для обычных слов: перевод, IPA и часть речи приходят из словаря.

Модель — из `AI_MODEL`, не хардкод. Кэш MeaningContent ключуется как
`meaning_id + cefr_level + prompt_version`. `source_context` в этот кэш не попадает.

### Файлы

`backend/app/integrations/ai/provider.py`,
`backend/app/integrations/ai/openai_provider.py`,
`backend/app/integrations/factory.py`.

### Действия

Протокол, Pydantic-схемы structured outputs, промпты и разбор `responses.parse` — **раздел 7**
[09-integrations-reference.md](09-integrations-reference.md). Сборка провайдеров через
`get_primary_dictionary_provider` / `get_ai_provider` — **раздел 8**.

Две разные операции, их нельзя смешать в один метод:

| Метод | Когда | Результат | Кэш |
| --- | --- | --- | --- |
| генерация контента | enrichment, нет definition/example | `definition` + `example` | MeaningContent |
| fallback значений | lookup пустой или «нет нужного значения» | до 3 Meaning с переводом | как обычный Meaning, без личного контекста в кэше |

Structured outputs обязательны: обычная просьба «верни JSON» периодически приносит markdown-ограждение.
Имя модели только из env. Промпт-версия из `AI_PROMPT_VERSION` — смена версии создаёт **новый**
MeaningContent, старый не перегенерируется сам.

Фабрика с `@lru_cache` — единственное место, где упоминаются классы Яндекса и OpenAI. Сервисы
импортируют протоколы и функции фабрики.

### Проверка

```bash
cd backend
uv run python -c "
from app.integrations.factory import get_ai_provider
provider = get_ai_provider()
print(type(provider).__name__)
"
```

Юнит-тесты — на фейковом провайдере, без сети и без ключа. Живой вызов OpenAI приберегите для шага 38
на одном слове, чтобы не жечь лимит.

### Коммит

`feat(backend): add ai provider protocol and openai adapter`

---

## Шаг 34. Сервис lookup: база → словарь → добор → AI

### Цель

Один сервис оркестрирует поиск значения. Роутер на шаге 35 только принимает JSON и отдаёт JSON.
Провайдеры сами по себе значений не сохраняют.

Порядок из продуктового плана, его нельзя переставлять:

1. нормализация;
2. PostgreSQL по `normalized_text`;
3. основной DictionaryProvider (Yandex);
4. fallback DictionaryProvider (Wiktionary) **только если не хватает IPA / перевода / определения**;
5. AI fallback, если словари пустые;
6. вернуть максимум 3 Meaning, `has_more`, при отсутствии точного совпадения — подсказку опечатки.

### Файлы

`backend/app/lexicon/lookup_service.py`, `backend/app/lexicon/lookup_models.py`,
`backend/tests/test_lookup_service.py`.

### Действия

`backend/app/lexicon/lookup_models.py` — результат для роутера, без ORM:

```python
from dataclasses import dataclass

from app.lexicon.models import LexemeType


@dataclass(frozen=True, slots=True)
class LookupMeaningView:
    meaning_id: int
    part_of_speech: str
    translation: str
    meaning_hint: str | None
    ipa: str | None
    source: str


@dataclass(frozen=True, slots=True)
class LookupResult:
    normalized_text: str
    lexeme_type: LexemeType
    meanings: tuple[LookupMeaningView, ...]
    has_more: bool
    suggestion: str | None
```

`backend/app/lexicon/lookup_service.py`:

```python
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.settings import Settings
from app.integrations.ai.provider import AIProvider
from app.integrations.dictionary.provider import DictionaryLookupResult, DictionaryProvider
from app.lexicon.lookup_models import LookupMeaningView, LookupResult
from app.lexicon.normalization import detect_lexeme_type, normalize_lexeme_text
from app.lexicon.repository import LexiconRepository
from app.users.models import User


@dataclass(frozen=True, slots=True)
class LookupQuery:
    text: str
    source_context: str | None
    offset: int
    use_ai_fallback: bool


class LexemeLookupService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        primary_provider: DictionaryProvider,
        fallback_provider: DictionaryProvider,
        ai_provider: AIProvider,
        native_language_id: int,
        learning_language_id: int,
    ) -> None:
        self._session = session
        self._settings = settings
        self._primary = primary_provider
        self._fallback = fallback_provider
        self._ai = ai_provider
        self._native_language_id = native_language_id
        self._learning_language_id = learning_language_id
        self._repository = LexiconRepository(session)
```

Оркестрация:

```python
    async def lookup(self, user: User, query: LookupQuery) -> LookupResult:
        normalized = normalize_lexeme_text(query.text)
        page_size = self._settings.lookup_meanings_page_size
        cefr = user.cefr_level.value if user.cefr_level else "A2"

        if query.use_ai_fallback:
            meanings = await self._ai_fallback_meanings(
                normalized, cefr, query.source_context
            )
            return self._paginate(normalized, meanings, query.offset, page_size)

        existing = await self._repository.find_by_normalized_text(
            self._learning_language_id, normalized
        )
        if existing is not None and existing.meanings:
            return self._paginate(
                normalized,
                self._to_views(existing),
                query.offset,
                page_size,
            )

        primary = await self._safe_lookup(self._primary, normalized)
        merged = primary
        if self._needs_fallback(merged):
            fallback = await self._safe_lookup(self._fallback, normalized)
            merged = self._merge_entries(merged, fallback)

        if merged.is_empty:
            suggestion = await self._repository.suggest_by_trigram(
                self._learning_language_id, normalized
            )
            if suggestion is not None:
                return LookupResult(
                    normalized_text=normalized,
                    lexeme_type=detect_lexeme_type(normalized),
                    meanings=(),
                    has_more=False,
                    suggestion=suggestion,
                )
            meanings = await self._ai_fallback_meanings(
                normalized, cefr, query.source_context
            )
            return self._paginate(normalized, meanings, query.offset, page_size)

        lexeme = await self._persist_dictionary_result(normalized, query.text, merged)
        await self._session.commit()
        return self._paginate(
            normalized, self._to_views(lexeme), query.offset, page_size
        )
```

Допишите вспомогательные методы рядом:

* `_safe_lookup` — ловит `ProviderPermanentError`, логирует, возвращает пустой `DictionaryLookupResult`;
  `ProviderTemporaryError` пробрасывает (роутер отдаст 503);
* `_needs_fallback` — `True`, если нет entries, либо у первого entry нет `ipa`, либо ни у одного
  meaning нет перевода или definition;
* `_merge_entries` — IPA с primary, definitions с fallback для той же `PartOfSpeech`, не дублируя
  уже существующие переводы;
* `_persist_dictionary_result` — `get_or_create_lexeme` + `add_meaning` с `LexicalSource.YANDEX`
  или `WIKTIONARY`;
* `_ai_fallback_meanings` — `MeaningFallbackRequest`, сохранение Meaning с `source=AI`, перевод на
  `native_language_id`;
* `_paginate` — срез `[offset:offset+page_size]`, `has_more = offset + page_size < len(all)`;
* `_to_views` — первый перевод, `meaning_hint` из второго синонима/подсказки если есть.

`source_context` уходит в AI **только** в `_ai_fallback_meanings`. В MeaningContent его нет — это
правило раздела 30 продуктового плана и шага 38.

Повторный lookup того же слова не должен снова бить Яндекс: ветка PostgreSQL срабатывает первой.
Именно поэтому lookup сохраняет Meaning сразу, а не после выбора пользователя. Выбор на шаге 37
передаёт уже существующий `meaning_id`.

Тесты `backend/tests/test_lookup_service.py` — на фейковых провайдерах, без сети:

```python
from app.integrations.dictionary.provider import (
    DictionaryEntry,
    DictionaryLookupResult,
    DictionaryMeaning,
    DictionaryTranslation,
    PartOfSpeech,
)


class FakeDictionary:
    def __init__(self, name: str, result: DictionaryLookupResult) -> None:
        self._name = name
        self._result = result

    @property
    def name(self) -> str:
        return self._name

    async def lookup(self, text: str) -> DictionaryLookupResult:
        return self._result


class EmptyAI:
    async def generate_meaning_content(self, request):
        raise AssertionError("content generation is not part of lookup")

    async def generate_fallback_meanings(self, request):
        raise AssertionError("AI should not run when dictionary returned meanings")
```

Сценарии, которые обязаны быть зелёными:

1. попадание в PostgreSQL — провайдеры не вызываются;
2. Яндекс нашёл значения — Wiktionary не вызывается, если IPA и перевод есть;
3. Яндекс без IPA — Wiktionary вызывается;
4. оба пустые, в базе есть `clarify` — на `clarfy` возвращается `suggestion="clarify"`, meanings пустые;
5. оба пустые и подсказки нет — вызывается AI fallback;
6. `use_ai_fallback=True` — словари не вызываются, AI получает `source_context`;
7. больше трёх значений — в первой странице 3, `has_more=True`;
8. `run` и `running` — два разных Lexeme.

### Проверка

```bash
cd backend
uv run pytest tests/test_lookup_service.py tests/test_normalization.py -v
uv run mypy app/lexicon
```

Если тест 2 вызывает Wiktionary при полном ответе Яндекса — `_needs_fallback` слишком жадный,
исправьте до эндпоинта.

### Коммит

`feat(backend): add lexeme lookup orchestration`

---

## Шаг 35. `POST /api/v1/lexemes/lookup`

### Цель

Клиент отправляет слово и получает страницу значений. Контракт —
[08-api-reference.md](08-api-reference.md), раздел lookup. Здесь реализация.

### Файлы

`backend/app/lexicon/schemas.py`, `backend/app/lexicon/router.py`, правка `main.py`.

### Действия

`backend/app/lexicon/schemas.py`:

```python
from pydantic import BaseModel, Field

from app.lexicon.models import LexemeType


class LexemeLookupRequest(BaseModel):
    text: str = Field(min_length=1, max_length=80)
    source_context: str | None = Field(default=None, max_length=500)
    offset: int = Field(default=0, ge=0, le=50)
    use_ai_fallback: bool = False


class LookupMeaningResponse(BaseModel):
    meaning_id: int
    part_of_speech: str
    translation: str
    meaning_hint: str | None
    ipa: str | None
    source: str


class LexemeLookupResponse(BaseModel):
    normalized_text: str
    lexeme_type: LexemeType
    meanings: list[LookupMeaningResponse]
    has_more: bool
    suggestion: str | None
```

Отдельные схемы на запрос и ответ — правило 21. `offset` обслуживает «Показать ещё»: клиент не
пересчитывает страницы сам, просто повторяет запрос с тем же `text` и большим смещением.
`use_ai_fallback=true` — кнопка «Нет нужного значения»: AI вызывается с `source_context`.

`backend/app/lexicon/router.py`:

```python
from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import AppSettings, CurrentUser, DbSession
from app.integrations.errors import ProviderTemporaryError
from app.integrations.factory import (
    get_ai_provider,
    get_fallback_dictionary_provider,
    get_primary_dictionary_provider,
)
from app.lexicon.lookup_service import LexemeLookupService, LookupQuery
from app.lexicon.normalization import NormalizationError
from app.lexicon.schemas import LexemeLookupRequest, LexemeLookupResponse, LookupMeaningResponse

router = APIRouter(prefix="/lexemes", tags=["lexemes"])


@router.post("/lookup", response_model=LexemeLookupResponse)
async def lookup_lexeme(
    body: LexemeLookupRequest,
    user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
) -> LexemeLookupResponse:
    if user.learning_language_id is None or user.native_language_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onboarding is not completed",
        )
    service = LexemeLookupService(
        session,
        settings,
        get_primary_dictionary_provider(),
        get_fallback_dictionary_provider(),
        get_ai_provider(),
        native_language_id=user.native_language_id,
        learning_language_id=user.learning_language_id,
    )
    try:
        result = await service.lookup(
            user,
            LookupQuery(
                text=body.text,
                source_context=body.source_context,
                offset=body.offset,
                use_ai_fallback=body.use_ai_fallback,
            ),
        )
    except NormalizationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except ProviderTemporaryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dictionary provider is temporarily unavailable",
        ) from error

    return LexemeLookupResponse(
        normalized_text=result.normalized_text,
        lexeme_type=result.lexeme_type,
        meanings=[
            LookupMeaningResponse(
                meaning_id=item.meaning_id,
                part_of_speech=item.part_of_speech,
                translation=item.translation,
                meaning_hint=item.meaning_hint,
                ipa=item.ipa,
                source=item.source,
            )
            for item in result.meanings
        ],
        has_more=result.has_more,
        suggestion=result.suggestion,
    )
```

Сервис не поднимает `HTTPException` — это граница HTTP. Единый обработчик доменных ошибок появится
на шаге 61; до тех пор маппинг остаётся в роутере, как на шаге 16.

Подключите роутер в `create_app()` рядом с auth/users/languages:

```python
from app.lexicon.router import router as lexicon_router

app.include_router(lexicon_router, prefix=settings.api_base_path)
```

Языки пользователя берутся из `CurrentUser`, не из тела запроса: клиенту нельзя подменить пару
языков и читать чужой кэш в другой геометрии.

### Проверка

Получите токен как на шаге 16 и:

```bash
TOKEN="<access_token>"

curl -s -X POST http://localhost:8000/api/v1/lexemes/lookup \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"bank"}' | python3 -m json.tool
```

В ответе не больше трёх `meanings`, у `bank` скорее всего `has_more: true`. Повтор:

```bash
curl -s -X POST http://localhost:8000/api/v1/lexemes/lookup \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"bank","offset":3}' | python3 -m json.tool
```

«Нет нужного значения»:

```bash
curl -s -X POST http://localhost:8000/api/v1/lexemes/lookup \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"bank","source_context":"He sat on the bank of the river.","use_ai_fallback":true}' \
  | python3 -m json.tool
```

Опечатка после того как `clarify` уже есть в базе:

```bash
curl -s -X POST http://localhost:8000/api/v1/lexemes/lookup \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"clarfy"}' | python3 -m json.tool
```

Без токена — 403. Пустая строка — 422. В `/docs` должен появиться тег `lexemes`.

### Коммит

`feat(backend): add lexeme lookup endpoint`

---

## Шаг 36. CRUD тем

### Цель

Пользователь создаёт, переименовывает и удаляет свои темы. «Все слова» этим API не создаются и не
возвращаются.

### Файлы

`backend/app/collections/{schemas.py,repository.py,service.py,router.py}`, правка `main.py`.

### Действия

Схемы — отдельные на create / update / response, как требует правило 21:

```python
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=240)


class CollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=240)


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_system: bool
    item_count: int
```

`item_count` в ORM нет — сервис считает его запросом `count(collection_items)` и передаёт в
`model_validate` через промежуточный объект или `CollectionResponse(..., item_count=n)`. Не делайте
N+1: список тем грузится одним запросом с `select(Collection, func.count())` и `group_by`.

Репозиторий:

* `list_for_user(user_id)` — только `user_id = :id AND is_system = false`;
* `get_owned(user_id, collection_id)` — `None`, если чужая или системная;
* `create`, `update`, `delete`.

Сервис:

* создать с `is_system=False`;
* запретить менять и удалять `is_system=True` (`PermissionDeniedError`);
* чужая тема → `EntityNotFoundError`, не 403 с «существует, но не ваша»;
* удаление темы не удаляет UserVocabularyItem.

Роутер `prefix="/collections"`:

```text
GET    /api/v1/collections
POST   /api/v1/collections
GET    /api/v1/collections/{collection_id}
PATCH  /api/v1/collections/{collection_id}
DELETE /api/v1/collections/{collection_id}
```

Все эндпоинты требуют `CurrentUser`. Подключите роутер в `main.py`.

Точные JSON-примеры — [08-api-reference.md](08-api-reference.md).

### Проверка

```bash
TOKEN="<access_token>"

curl -s -X POST http://localhost:8000/api/v1/collections \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Книги","description":"из чтения"}' | python3 -m json.tool

curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/collections | python3 -m json.tool
```

В списке нет «Все слова». Повторный POST с тем же именем допустим — уникальность имени в MVP не
требуем, пользователь отличит темы сам.

Удаление:

```bash
curl -si -X DELETE http://localhost:8000/api/v1/collections/<id> \
  -H "Authorization: Bearer $TOKEN" | head -1
```

Ожидается 204. Карточки, если уже были, остаются в `user_vocabulary_items`.

### Коммит

`feat(backend): add collections crud`

---

## Шаг 37. Создание `UserVocabularyItem` и постановка задачи

### Цель

Выбор Meaning создаёт персональную карточку, привязывает её к темам и ставит Celery-задачу
обогащения. Повтор того же значения тем же пользователем не создаёт дубль.

### Файлы

`backend/app/vocabulary/{schemas.py,repository.py,service.py,router.py}`,
правка `backend/app/common/errors.py`, правка `main.py`.

### Действия

Добавьте в `common/errors.py`:

```python
class DuplicateEntityError(ApplicationError):
    pass
```

На уникальном `(user_id, meaning_id)` гонка двух одинаковых POST возможна с Mini App. Сервис ловит
`IntegrityError`, находит существующую карточку и добавляет её в запрошенные темы — тот же приём,
что `_create_user_handling_race` на шаге 15.

Схемы:

```python
from uuid import UUID

from pydantic import BaseModel, Field

from app.vocabulary.models import EnrichmentStatus


class VocabularyItemCreate(BaseModel):
    meaning_id: int
    source_context: str | None = Field(default=None, max_length=500)
    collection_ids: list[UUID] = Field(default_factory=list)


class VocabularyItemSummaryResponse(BaseModel):
    id: UUID
    text: str
    translation: str
    lexeme_type: str
    enrichment_status: EnrichmentStatus
```

Полная карточка — на шаге 39. Create возвращает summary: фронту достаточно id и статуса, чтобы
уйти назад в тему и начать поллинг.

Сервис `VocabularyItemService.create`:

1. загрузить Meaning с Lexeme (нет → `EntityNotFoundError`);
2. найти существующий UserVocabularyItem по паре user+meaning;
3. если нет — вставить со статусом `PENDING`, `source_context` из запроса;
4. для каждого `collection_id` проверить владение и вставить `CollectionItem` (игнорировать дубль
   связи);
5. `commit`;
6. `enrich_vocabulary_item.delay(str(item.id))`;
7. вернуть item.

Пустой `collection_ids` допустим: карточка живёт в «Всех словах». Одна карточка — много тем.

Пока задачи шага 38 нет, `delay` уже можно вызывать: в `enrichment/tasks.py` с шага 17 замените
заглушку `count_users` на объявление с тем же именем, что будет в 38, и телом `pass` / логом
«not implemented». Иначе POST упадёт на `NotRegistered`.

Роутер:

```text
POST /api/v1/vocabulary
```

Только `CurrentUser`. `meaning_id` из тела, не из URL.

### Проверка

```bash
TOKEN="<access_token>"
MEANING_ID=<id из lookup>
COLLECTION_ID=<id темы>

curl -s -X POST http://localhost:8000/api/v1/vocabulary \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"meaning_id\": $MEANING_ID, \"collection_ids\": [\"$COLLECTION_ID\"]}" \
  | python3 -m json.tool
```

Повтор того же тела возвращает ту же карточку, в `user_vocabulary_items` одна строка:

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "
select id, meaning_id, enrichment_status from user_vocabulary_items;
"
```

В логах worker — принятая задача (пока пустая). Две темы в `collection_ids` → две строки в
`collection_items`, один `user_vocabulary_item_id`.

### Коммит

`feat(backend): create vocabulary items and enqueue enrichment`

---

## Шаг 38. Celery enrichment: лок, уникальность, ретраи, PARTIAL

### Цель

После выбора значения карточка добирается в фоне: недостающие словарные поля, аудио mp3,
definition/example. Пропавшее аудио не валит всю карточку.

Задача Celery — тонкая обёртка. Логика в `EnrichmentService`, её же вызывают тесты без брокера.
Требование раздела 29 правил и [01-primer-python-backend.md](01-primer-python-backend.md), раздел 7.

Пайплайн из продуктового плана:

```text
check existing MeaningContent
 → dictionary missing fields
 → audio (ogg→mp3)
 → AI definition/example if missing
 → validate
 → READY / PARTIAL / FAILED
```

### Файлы

`backend/app/enrichment/locks.py`,
`backend/app/enrichment/service.py`,
правка `backend/app/enrichment/tasks.py`,
`backend/tests/test_enrichment_service.py`.

### Действия

`backend/app/enrichment/locks.py`:

```python
from redis.asyncio import Redis

LOCK_TTL_SECONDS = 90


class MeaningContentLock:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, meaning_id: int, cefr_level: str, prompt_version: str) -> str:
        return f"meaning_content:{meaning_id}:{cefr_level}:{prompt_version}"

    async def acquire(self, meaning_id: int, cefr_level: str, prompt_version: str) -> bool:
        return bool(
            await self._redis.set(
                self._key(meaning_id, cefr_level, prompt_version),
                "1",
                nx=True,
                ex=LOCK_TTL_SECONDS,
            )
        )

    async def release(self, meaning_id: int, cefr_level: str, prompt_version: str) -> None:
        await self._redis.delete(self._key(meaning_id, cefr_level, prompt_version))
```

`SET NX EX` — атомарный лок без отдельного `SETNX` + `EXPIRE`. TTL 90 с больше `task_soft_time_limit`
(150 с на worker — если задача жива дольше лока, второй worker может начать генерацию: тогда спасет
unique constraint).

`EnrichmentService.run(item_id)` в одном предложении:

1. загрузить UserVocabularyItem + Meaning + Lexeme + translations + contents (`selectinload`);
2. выставить `ENRICHING` и commit;
3. если у Lexeme нет IPA/перевода — добрать словарём (primary, при дырах fallback). Недостающее
   дописать в те же строки, не создавая второй Lexeme;
4. если нет `audio_url` и тип `word` — `AudioProvider.find_pronunciation` + storage с ffmpeg.
   `None` не ошибка;
5. найти MeaningContent по `(meaning_id, user.cefr_level, prompt_version)`;
6. если нет или `FAILED` — взять лок, вставить строку со статусом `GENERATING`, вызвать AI,
   заполнить definition/example, статус `READY`. Если лок не взят — подождать 2–3 с и перечитать.
   Если `IntegrityError` на unique — перечитать существующую строку;
7. посчитать финальный статус карточки и сохранить.

Правило статусов карточки:

| Есть перевод | definition + example | Итог |
| --- | --- | --- |
| нет | неважно | `FAILED` |
| да | да | `READY` (аудио необязательно) |
| да | нет | `PARTIAL` |

Отсутствие mp3 при готовом тексте — `READY`. Пользователь учит слово без звука. Отсутствие
definition — `PARTIAL`: этап «написание по definition» на неделе 3 это слово пропустит или покажет
перевод. Не ставьте `FAILED` из-за Commons.

`source_context` в промпт генерации MeaningContent **не передавать**. Он уже использован на lookup
для выбора/создания Meaning.

Задача:

```python
import logging
from uuid import UUID

from app.common.celery_app import celery_app
from app.common.settings import get_settings
from app.common.task_runtime import run_async_task, task_db_session
from app.enrichment.locks import MeaningContentLock
from app.enrichment.service import EnrichmentService
from app.integrations.errors import ProviderTemporaryError
from app.integrations.factory import (
    get_ai_provider,
    get_audio_provider,
    get_audio_storage,
    get_fallback_dictionary_provider,
    get_primary_dictionary_provider,
)
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


@celery_app.task(
    name="enrichment.enrich_vocabulary_item",
    bind=True,
    max_retries=4,
    autoretry_for=(ProviderTemporaryError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    acks_late=True,
)
def enrich_vocabulary_item(self, vocabulary_item_id: str) -> None:
    run_async_task(lambda: _enrich(UUID(vocabulary_item_id)))


async def _enrich(vocabulary_item_id: UUID) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        async with task_db_session() as session:
            await EnrichmentService(
                session=session,
                settings=settings,
                primary_dictionary=get_primary_dictionary_provider(),
                fallback_dictionary=get_fallback_dictionary_provider(),
                audio_provider=get_audio_provider(),
                audio_storage=get_audio_storage(),
                ai_provider=get_ai_provider(),
                lock=MeaningContentLock(redis),
            ).run(vocabulary_item_id)
    finally:
        await redis.aclose()
```

`autoretry_for` + `retry_backoff` — экспонента с потолком 60 с, без бесконечных циклов. Постоянные
ошибки провайдера не ретраятся: сервис сам ставит `PARTIAL`/`FAILED`. После исчерпания попыток
Celery не должен оставлять карточку в `ENRICHING` навсегда — в сервисе `try/finally` или обработка
в `on_failure` колбэке задачи:

```python
@celery_app.task(bind=True, name="enrichment.mark_failed_if_stuck")
def mark_item_failed(self, uuid_str: str, exc, task_id, args, kwargs, einfo) -> None:
    run_async_task(lambda: _mark_partial_or_failed(UUID(uuid_str)))
```

Проще: в конце `run()` всегда пишется терминальный статус. Если `ProviderTemporaryError` летит
наружу до записи — `on_failure` переводит `ENRICHING` → `PARTIAL`, когда перевод уже есть.

Два пользователя, выбравшие одно Meaning на одном CEFR, должны получить одну строку MeaningContent.
Проверьте это тестом: два вызова `run` параллельно (или второй сразу после вставки `GENERATING`) —
`count(*)` = 1.

Удалите `count_users` из `tasks.py`, если больше не нужен.

### Проверка

```bash
cd infra
docker compose logs -f celery-worker
```

Создайте карточку шагом 37, дождитесь в логах worker JSON с `vocabulary_item_id` и финальным статусом.

```bash
docker compose exec postgres psql -U vocabulary -d vocabulary -c "
select uvi.enrichment_status, l.text, l.ipa, l.audio_url,
       mc.definition is not null as has_definition,
       mc.example is not null as has_example,
       mc.prompt_version
from user_vocabulary_items uvi
join meanings m on m.id = uvi.meaning_id
join lexemes l on l.id = m.lexeme_id
left join meaning_contents mc on mc.meaning_id = m.id;
"
```

Аудиофайл:

```bash
docker compose exec backend ls -l /app/media/audio | head
curl -sI http://localhost:8080/media/audio/<имя>.mp3 | head -5
```

`Content-Type` должен быть `audio/mpeg`, не `application/ogg`. Повторное добавление того же Meaning
другим тестовым пользователем (или тем же после DELETE) не должно создать второй MeaningContent.

Напишите тесты сервиса с фейковыми провайдерами:

* аудио возвращает `None` → статус не `FAILED`;
* AI падает постоянной ошибкой, перевод есть → `PARTIAL`;
* MeaningContent уже READY → AI не вызывается;
* unique conflict обрабатывается без исключения наружу.

```bash
cd backend
uv run pytest tests/test_enrichment_service.py -v
```

### Коммит

`feat(backend): add enrichment pipeline with lock and partial status`

---

## Шаг 39. Эндпоинты словаря: список, карточка, заметка, удаление

### Цель

Список отдаёт краткие карточки, полная карточка грузится отдельно. Удаление из темы и из словаря —
разные операции.

### Файлы

правка `backend/app/vocabulary/{schemas.py,service.py,router.py}`,
правка `backend/app/collections/router.py`.

### Действия

Эндпоинты:

```text
GET    /api/v1/vocabulary?collection_id=<uuid необязательно>
GET    /api/v1/vocabulary/{item_id}
PATCH  /api/v1/vocabulary/{item_id}
DELETE /api/v1/vocabulary/{item_id}
DELETE /api/v1/collections/{collection_id}/items/{item_id}
```

Без `collection_id` — «Все слова». С ним — слова темы. Чужой `collection_id` → 404.

Список (поля из продуктового сценария 7.4): `id`, `text`, `translation`, `lexeme_type`,
`enrichment_status`. Не тащите definition/example/audio в ленту — это полная карточка.

Полная карточка (сценарий 7.5):

```python
class VocabularyItemResponse(BaseModel):
    id: UUID
    text: str
    lexeme_type: str
    translation: str
    ipa: str | None
    audio_url: str | None
    part_of_speech: str
    definition: str | None
    example: str | None
    source_context: str | None
    personal_note: str | None
    enrichment_status: EnrichmentStatus
    collection_ids: list[UUID]
```

`definition` / `example` — из MeaningContent **уровня пользователя** (`user.cefr_level` + текущий
`prompt_version`). Чужой CEFR не подмешивать. Если контента ещё нет — поля `null`, статус
`PENDING`/`ENRICHING`.

PATCH принимает только персональное:

```python
class VocabularyItemUpdate(BaseModel):
    personal_note: str | None = Field(default=None, max_length=500)
```

Нельзя через PATCH менять translation, meaning_id, enrichment_status.

`DELETE /vocabulary/{id}` удаляет UserVocabularyItem → каскад `collection_items`. Lexeme/Meaning
остаются. `DELETE .../collections/{id}/items/{item_id}` снимает только связь; карточка остаётся
в «Всех словах».

Списки грузите одним запросом с join Lexeme + Translation, без N+1. Фильтр `user_id = current`.

Точные примеры JSON — [08-api-reference.md](08-api-reference.md).

### Проверка

```bash
TOKEN="<access_token>"
ITEM=<uuid>
COLLECTION=<uuid>

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/vocabulary" | python3 -m json.tool

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/vocabulary?collection_id=$COLLECTION" | python3 -m json.tool

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/vocabulary/$ITEM" | python3 -m json.tool

curl -s -X PATCH http://localhost:8000/api/v1/vocabulary/$ITEM \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"personal_note":"из 3 главы"}' | python3 -m json.tool

curl -si -X DELETE \
  "http://localhost:8000/api/v1/collections/$COLLECTION/items/$ITEM" \
  -H "Authorization: Bearer $TOKEN" | head -1

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/vocabulary/$ITEM" | python3 -m json.tool
```

После удаления из темы полная карточка ещё открывается, `collection_ids` её больше не содержит.
После `DELETE /vocabulary/{id}` — 404.

Чужой id (случайный UUID) — 404, не 403.

### Коммит

`feat(backend): add vocabulary list card update and delete`

---

## Шаг 40. Frontend: главный экран и CRUD тем

### Цель

После onboarding пользователь видит «Все слова», свои темы, кнопку «Создать тему» и заглушку
«Неправильные глаголы». Заглушку главного экрана с шага 22 заменяем.

Перед шагом освежите [02-primer-angular.md](02-primer-angular.md), разделы 3–7.

### Файлы

```text
frontend/src/app/features/collections/
├── collections-api.ts
├── collections-page.ts
├── collections-page.html
├── collections-page.scss
├── collection-page.ts
├── collection-page.html
├── collection-page.scss
├── collection-form-page.ts
├── collection-form-page.html
└── collection-form-page.scss
```

правка `app.routes.ts`. Компоненты HttpClient не вызывают.

### Действия

`collections-api.ts`:

```typescript
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface Collection {
  readonly id: string;
  readonly name: string;
  readonly description: string | null;
  readonly is_system: boolean;
  readonly item_count: number;
}

export interface CollectionWrite {
  readonly name: string;
  readonly description: string | null;
}

@Injectable({ providedIn: 'root' })
export class CollectionsApi {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiBaseUrl}/collections`;

  listCollections(): Observable<Collection[]> {
    return this.http.get<Collection[]>(this.base);
  }

  getCollection(id: string): Observable<Collection> {
    return this.http.get<Collection>(`${this.base}/${id}`);
  }

  createCollection(body: CollectionWrite): Observable<Collection> {
    return this.http.post<Collection>(this.base, body);
  }

  updateCollection(id: string, body: CollectionWrite): Observable<Collection> {
    return this.http.patch<Collection>(`${this.base}/${id}`, body);
  }

  deleteCollection(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
```

Поля в `snake_case`, как в ответе API — тот же подход, что `UserProfile` на шаге 20.

Главный экран — контейнер на signals + `AsyncState` из шага 21. Карточка «Все слова» **не** приходит
с backend: это локальный пункт навигации на `/vocabulary`. Карточка «Неправильные глаголы» ведёт
на заглушку «появится на неделе 3» (маршрут можно уже зарезервировать).

Форма создания/редактирования — Reactive Forms, не Signal Forms и не ngModel. Поля `name` (required,
max 80) и `description` (max 240). Кнопка сабмита неактивна, пока форма невалидна — как onboarding.

Список слов темы (`collection-page`) на этом шаге может показать имя темы, кнопку «Добавить слово»
и краткий список через `VocabularyApi.listSummaries({ collectionId })` — сам API появится в шаге 41,
поэтому сейчас достаточно имени, пустого состояния и кнопки, ведущей на `/collections/:id/add`.

Маршруты:

```typescript
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
  {
    path: 'collections/new',
    canActivate: [onboardingGuard],
    loadComponent: () =>
      import('./features/collections/collection-form-page').then((m) => m.CollectionFormPage),
  },
  {
    path: 'collections/:collectionId',
    canActivate: [onboardingGuard],
    loadComponent: () =>
      import('./features/collections/collection-page').then((m) => m.CollectionPage),
  },
  { path: '**', redirectTo: '' },
];
```

Стили — в `.scss` компонента, токены из `styles.scss` шага 19. Без `style=""`. Сетка карточек тем —
простая, Mini App узкий.

Удаление темы: подтверждение через Telegram `showConfirm` или простой диалог. После DELETE —
навигация на главную.

### Проверка

```bash
cd frontend
npx tsc --noEmit
```

Откройте Mini App (или временно браузер, как на шаге 22):

1. главный экран показывает «Все слова» и «Создать тему»;
2. создание темы возвращает на главную, тема в списке;
3. открытие темы показывает пустое состояние;
4. переименование сохраняется;
5. удаление убирает тему, «Все слова» на месте.

Если «Все слова» пришли с `GET /collections` — вы создали лишнюю запись, уберите.

### Коммит

`feat(frontend): add home screen and collections crud`

---

## Шаг 41. Frontend: добавление слова и выбор значения

### Цель

Из темы (и из «Всех слов») пользователь вводит слово, видит до трёх Meaning, может показать ещё,
сказать «нет нужного значения» и сохранить выбор.

### Файлы

```text
frontend/src/app/features/vocabulary/
├── vocabulary-api.ts
├── add-word-page.ts
├── add-word-page.html
├── add-word-page.scss
├── meaning-selector.ts
├── meaning-selector.html
└── meaning-selector.scss
```

правка маршрутов.

### Действия

`vocabulary-api.ts`:

```typescript
import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export type EnrichmentStatus = 'PENDING' | 'ENRICHING' | 'READY' | 'PARTIAL' | 'FAILED';
export type LexemeType = 'word' | 'phrase';

export interface LookupMeaning {
  readonly meaning_id: number;
  readonly part_of_speech: string;
  readonly translation: string;
  readonly meaning_hint: string | null;
  readonly ipa: string | null;
  readonly source: string;
}

export interface LexemeLookupResponse {
  readonly normalized_text: string;
  readonly lexeme_type: LexemeType;
  readonly meanings: readonly LookupMeaning[];
  readonly has_more: boolean;
  readonly suggestion: string | null;
}

export interface LexemeLookupRequest {
  readonly text: string;
  readonly source_context?: string | null;
  readonly offset?: number;
  readonly use_ai_fallback?: boolean;
}

export interface VocabularyItemSummary {
  readonly id: string;
  readonly text: string;
  readonly translation: string;
  readonly lexeme_type: LexemeType;
  readonly enrichment_status: EnrichmentStatus;
}

export interface VocabularyItemCreate {
  readonly meaning_id: number;
  readonly source_context?: string | null;
  readonly collection_ids: readonly string[];
}

@Injectable({ providedIn: 'root' })
export class VocabularyApi {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  lookup(request: LexemeLookupRequest): Observable<LexemeLookupResponse> {
    return this.http.post<LexemeLookupResponse>(`${this.base}/lexemes/lookup`, request);
  }

  listSummaries(collectionId?: string): Observable<VocabularyItemSummary[]> {
    const params = collectionId
      ? new HttpParams().set('collection_id', collectionId)
      : undefined;
    return this.http.get<VocabularyItemSummary[]>(`${this.base}/vocabulary`, { params });
  }

  createItem(body: VocabularyItemCreate): Observable<VocabularyItemSummary> {
    return this.http.post<VocabularyItemSummary>(`${this.base}/vocabulary`, body);
  }
}
```

Состояние селектора — отдельный тип, не набор булевых флагов. Иначе легко получить «грузится и
ошибка одновременно»:

```typescript
export type MeaningSelectorView =
  | { readonly status: 'idle' }
  | { readonly status: 'looking_up' }
  | {
      readonly status: 'meanings';
      readonly meanings: readonly LookupMeaning[];
      readonly hasMore: boolean;
      readonly offset: number;
    }
  | { readonly status: 'suggestion'; readonly suggestion: string }
  | { readonly status: 'empty' }
  | { readonly status: 'saving' }
  | { readonly status: 'error'; readonly error: ApiError };
```

`MeaningSelector` — презентационный компонент: `@Input` текущий view, `@Output` выбора Meaning,
«показать ещё», «нет нужного значения», клик по подсказке. Lookup и POST не живут в нём.

`AddWordPage` — контейнер:

* Reactive Form: `text` (required, max 80), `source_context` (max 500);
* чекбоксы тем — список из `CollectionsApi`, плюс тема, из которой пришли, уже отмечена
  (`collectionId` из маршрута). Из «Всех слов» можно не выбирать тему;
* «Найти значение» → `VocabularyApi.lookup`, запись в `signal<MeaningSelectorView>`;
* «Показать ещё» → тот же `text` / `source_context`, `offset = текущий + meanings.length`,
  **добавить** к уже показанным, не заменить;
* подсказка опечатки подставляет `suggestion` в форму и повторяет lookup;
* «Нет нужного значения» → `use_ai_fallback: true`;
* выбор Meaning → `createItem`, затем навигация назад в тему/«Все слова».

Не вызывайте lookup на каждый ввод. Только по кнопке. Telegram Mini App на медленной сети, лишний
Яндекс и AI стоят денег.

Маршруты:

```text
collections/:collectionId/add  → AddWordPage
vocabulary                     → список «Все слова» (можно расширить collection-page без id)
vocabulary/add                 → AddWordPage без предвыбранной темы
```

Для списка «Все слова» переиспользуйте разметку списка темы: `text`, `translation`, бейдж статуса.
Клик по строке — на карточку шага 42 (пока можно вести на `/vocabulary/:itemId`).

### Проверка

```bash
cd frontend
npx tsc --noEmit
```

В Mini App:

1. тема → «Добавить слово» → `bank` → три значения «банк / берег / …»;
2. «Показать ещё» дописывает следующие, кнопка пропадает когда `has_more=false`;
3. «Нет нужного значения» при заполненном контексте даёт AI-значения;
4. выбор сохраняет карточку, в теме появляется строка со статусом `PENDING` или `ENRICHING`;
5. повторный выбор того же Meaning не создаёт вторую строку.

Негатив: пустой ввод не бьёт API; ошибка сети показывает текст из `ApiError`, не сырой HTTP.

### Коммит

`feat(frontend): add word lookup and meaning selection`

---

## Шаг 42. Frontend: полная карточка, аудио и поллинг enrichment

### Цель

Пользователь открывает карточку, видит «Подготавливаем…», дожидается READY/PARTIAL и слушает mp3.

### Файлы

```text
frontend/src/app/features/vocabulary/
├── vocabulary-api.ts          дополнить get/patch/delete
├── word-card-page.ts
├── word-card-page.html
├── word-card-page.scss
├── audio-player.ts
├── audio-player.html
└── audio-player.scss
```

### Действия

Дополните `VocabularyApi`:

```typescript
export interface VocabularyItem {
  readonly id: string;
  readonly text: string;
  readonly lexeme_type: LexemeType;
  readonly translation: string;
  readonly ipa: string | null;
  readonly audio_url: string | null;
  readonly part_of_speech: string;
  readonly definition: string | null;
  readonly example: string | null;
  readonly source_context: string | null;
  readonly personal_note: string | null;
  readonly enrichment_status: EnrichmentStatus;
  readonly collection_ids: readonly string[];
}

export interface VocabularyItemUpdate {
  readonly personal_note: string | null;
}

getItem(id: string): Observable<VocabularyItem> {
  return this.http.get<VocabularyItem>(`${this.base}/vocabulary/${id}`);
}

updateItem(id: string, body: VocabularyItemUpdate): Observable<VocabularyItem> {
  return this.http.patch<VocabularyItem>(`${this.base}/vocabulary/${id}`, body);
}

deleteItem(id: string): Observable<void> {
  return this.http.delete<void>(`${this.base}/vocabulary/${id}`);
}

removeFromCollection(collectionId: string, itemId: string): Observable<void> {
  return this.http.delete<void>(
    `${this.base}/collections/${collectionId}/items/${itemId}`,
  );
}
```

Поллинг — в странице карточки, не в API-слое и не через `setInterval` без очистки. Статусы
`PENDING` и `ENRICHING` опрашивают `GET` каждые 2 с, максимум ~60 раз. Останавливаются на
`READY` | `PARTIAL` | `FAILED` и при уничтожении компонента (`DestroyRef`).

Члены `WordCardPage` — `watchEnrichment()` вызывайте из `ngOnInit`:

```typescript
import { DestroyRef, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval, startWith, switchMap, take, takeWhile } from 'rxjs';

import { toApiError } from '../../core/api/api-error';
import { AsyncState, errorState, successState } from '../../core/api/async-state';
import { EnrichmentStatus, VocabularyApi, VocabularyItem } from './vocabulary-api';

const TERMINAL: ReadonlySet<EnrichmentStatus> = new Set(['READY', 'PARTIAL', 'FAILED']);

private readonly vocabularyApi = inject(VocabularyApi);
private readonly destroyRef = inject(DestroyRef);
readonly itemId = input.required<string>();
protected readonly card = signal<AsyncState<VocabularyItem>>({ status: 'loading' });

private watchEnrichment(): void {
  const id = this.itemId();
  interval(2000)
    .pipe(
      startWith(0),
      switchMap(() => this.vocabularyApi.getItem(id)),
      takeWhile((item) => !TERMINAL.has(item.enrichment_status), true),
      take(60),
      takeUntilDestroyed(this.destroyRef),
    )
    .subscribe({
      next: (item) => this.card.set(successState(item)),
      error: (error: unknown) => this.card.set(errorState(toApiError(error))),
    });
}
```

`itemId` — `input.required<string>()` из маршрута (`withComponentInputBinding` уже включён на шаге 19,
параметр называйте `itemId` и в `path: 'vocabulary/:itemId'`).

Пока статус не терминальный, блок definition/example заменён текстом «Подготавливаем карточку…».
Кнопка «Начать занятие» на неделе 3 будет неактивна для `PENDING`/`ENRICHING`/`FAILED`; сейчас её нет.

`AudioPlayer` — `<audio [src]="src()">` плюс кнопка play/pause. `src` — `audio_url` с backend
(уже mp3 и публичный `/media/...`). Не подставляйте ogg. Если `audio_url` null на READY/PARTIAL —
плеер не рендерится, карточка остаётся читаемой.

Личная заметка — маленькая Reactive Form, PATCH по blur или кнопке «Сохранить». Удаление из текущей
темы vs из словаря — две кнопки с разным confirm-текстом.

Шаблон карточки показывает: word/phrase, translation, IPA, audio, part of speech, definition,
example, source_context, personal_note, список тем. Стили в scss.

Маршрут `vocabulary/:itemId` за `onboardingGuard`.

### Проверка

Сквозной путь недели — в Mini App, не скриншотом:

1. создать тему «Книги»;
2. добавить `clarify` (или `bank`);
3. выбрать Meaning;
4. открыть карточку — виден статус подготовки;
5. через несколько секунд status `READY` или `PARTIAL`, появились definition и example;
6. если есть `audio_url` — play в Telegram на телефоне (проверка mp3; iOS — главный резон шага 32);
7. заметка сохраняется после переоткрытия;
8. удаление из темы оставляет карточку в «Всех словах»; удаление из словаря убирает её везде.

```bash
cd frontend
npx tsc --noEmit
npm test -- --watch=false
cd ../backend
uv run pytest -v
```

Если поллинг не останавливается — утечка запросов, проверьте `takeWhile` и `takeUntilDestroyed`.
Если звука нет только в iPhone — в карточке ogg, вернитесь к шагу 32.

### Коммит

`feat(frontend): add vocabulary card audio and enrichment polling`

---

## Definition of Done недели 2

Проверьте каждый пункт вживую в Mini App, не по памяти:

- [ ] Пользователь создаёт тему с именем и необязательным описанием
- [ ] «Все слова» видны на главной и **не** являются строкой в таблице `collections`
- [ ] Пользователь вводит слово, backend нормализует (`Clarify` = `clarify`)
- [ ] Lookup возвращает не больше 3 значений, есть «Показать ещё» при `has_more`
- [ ] «Нет нужного значения» вызывает AI с `source_context`
- [ ] Опечатка `clarfy` предлагает `clarify`, если такое Lexeme уже есть
- [ ] `run` и `running` сохраняются как разные Lexeme
- [ ] Выбор Meaning создаёт один UserVocabularyItem; повтор не дублирует строку
- [ ] Карточка может состоять в нескольких темах
- [ ] Celery enrichment доводит карточку до `READY` или `PARTIAL`
- [ ] Отсутствие аудио не ставит `FAILED`
- [ ] MeaningContent один на тройку meaning + CEFR + prompt_version
- [ ] Полная карточка показывает перевод, IPA, definition, example, заметку
- [ ] Аудио — mp3 по `/media/`, воспроизводится в WebView
- [ ] Удаление из темы ≠ удаление из словаря
- [ ] Компоненты не вызывают `HttpClient` напрямую
- [ ] В исходниках нет комментариев

### Что делать, если неделя затянулась

Режьте в таком порядке (как в корневом README):

1. Wiktionary (шаг 31) — работайте на Yandex + AI;
2. конвертация аудио (шаг 32) — карточки без звука, статус `READY` при наличии текста;
3. «Показать ещё» — всегда три значения.

Никогда не режьте: нормализацию и unique `user_id+meaning_id` (27, 37), лок и unique на
MeaningContent (38), разделение «Все слова» и Collection (36, 40).

Дальше: [05-week3-study.md](05-week3-study.md), шаг 43.
