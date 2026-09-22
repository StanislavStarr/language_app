# Неделя 3 — Study (шаги 43–57)

## Цель недели

К концу недели пользователь выбирает тему, количество слов и режим (случайно / вручную), проходит
занятие целиком, закрывает Telegram, открывает Mini App снова — и продолжает с сохранённого этапа и
слова. Неправильные глаголы работают отдельным системным flow.

Ориентировочное время: 28 часов.

Backend — источник истины для длительно живущего состояния сессии. Frontend держит только UI-состояние
текущего экрана: попытки, выбранные пары, раскрытый перевод. После перезапуска Mini App это
UI-состояние сбрасывается, а этап, индекс слова и сами упражнения приходят с сервера теми же.

Перед шагами 50–57 откройте [02-primer-angular.md](02-primer-angular.md) — разделы про signals,
`inject()`, store и Vitest. Контракты ответов не копируйте сюда: полные примеры запросов и тел —
в [08-api-reference.md](08-api-reference.md). Поля таблиц, индексы и рецепты Alembic —
в [07-database-reference.md](07-database-reference.md).

---

## Что уже должно быть готово

Неделя 2 закрыта: `Lexeme` / `Meaning` / `Translation` / `MeaningContent`, `UserVocabularyItem`,
темы, карточка, аудио. Для отладки study достаточно нескольких карточек `READY` или `PARTIAL` с
переводом — пустая тема занятие не стартует.

---

## Решения недели — зафиксировать один раз

Эти решения действуют во всех шагах 43–57. Не вводите второй способ «на всякий случай».

| Тема | Решение | Почему |
| --- | --- | --- |
| Активная сессия | Одна `IN_PROGRESS` на пользователя. `POST` возвращает её, если она есть, и не создаёт новую | Иначе restore невозможен: непонятно, какую сессию продолжать |
| Упражнения | Генерируются на сервере в момент создания, кладутся в `exercise_payload` (JSONB), `GET` отдаёт тот же снимок | Restore должен показать те же пары matching и то же предложение с пропуском. Античит в MVP не цель |
| Прогресс | `PATCH` пишет `current_stage` и `current_item_index`. Попытки и выбранные пары на сервер не едут | После перезапуска matching начинается заново на том же наборе; индекс слова и этап сохраняются |
| Кто учится | `READY` всегда, если есть перевод. `PARTIAL` — если есть перевод. `PENDING` / `ENRICHING` / `FAILED` — нет | Карточка без перевода не проходит matching и definition. `FAILED` в этом проекте значит «пользоваться нельзя» |
| Фразы | Этап `SENTENCE` пропускается: в payload у phrase нет sentence-задания, последовательность этапов его не содержит | Продуктовый план: сокращённый flow |
| Глаголы | Отдельный `kind=IRREGULAR_VERBS`, не `UserVocabularyItem`. Системная тема — точка входа в UI | Глагол — три формы и отдельное аудио, это не карточка слова пользователя |
| Frontend state | `StudySessionStore` на signals, `providedIn: 'root'` нет — store живёт на странице занятия | NgRx не используем. Синглтон на всё приложение сохранит чужой прогресс при смене пользователя |
| Проверка ответа | Trim + схлопывание пробелов + lowercase. Без опечаток, стемминга и «похожести» | «Строгая проверка» из плана. Регистр не наказываем — это не знание слова |

---

## Шаг 43. Модели `StudySession` и `StudySessionItem` + миграция

### Цель

В PostgreSQL есть таблицы сессии и её состава. У сессии есть статус, текущий этап, индекс текущего
слова, снимок упражнений, время старта и завершения.

### Файлы

```text
backend/app/study/__init__.py
backend/app/study/models.py
backend/app/common/models_registry.py    правка: импорт новых моделей
backend/alembic/versions/*_add_study_sessions.py
```

Полный список колонок, CHECK-ограничений и индексов — в [07-database-reference.md](07-database-reference.md),
раздел `StudySession` / `StudySessionItem`. Ниже — рабочая модель, с которой начинается неделя.
Три поля, которых нет в скелете продуктового плана, обязательны для restore:

* `kind` — обычное занятие или неправильные глаголы;
* `current_item_index` — какое слово внутри этапа;
* `exercise_payload` — неизменяемый снимок заданий.

Без них шаг 57 нельзя сделать честно.

### Действия

Создайте пакет и модели:

```python
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.database import Base
from app.common.mixins import TimestampMixin


class StudySessionKind(StrEnum):
    VOCABULARY = "VOCABULARY"
    IRREGULAR_VERBS = "IRREGULAR_VERBS"


class StudySessionStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class StudyStage(StrEnum):
    INTRODUCTION = "INTRODUCTION"
    MATCHING = "MATCHING"
    SENTENCE = "SENTENCE"
    DEFINITION = "DEFINITION"
    VERB_CONJUGATION = "VERB_CONJUGATION"
    VERB_FORM_PROMPT = "VERB_FORM_PROMPT"


class StudySession(Base, TimestampMixin):
    __tablename__ = "study_sessions"
    __table_args__ = (
        Index(
            "uq_study_sessions_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'IN_PROGRESS'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL")
    )
    kind: Mapped[StudySessionKind] = mapped_column(
        SqlEnum(StudySessionKind, name="study_session_kind", native_enum=True),
        nullable=False,
    )
    status: Mapped[StudySessionStatus] = mapped_column(
        SqlEnum(StudySessionStatus, name="study_session_status", native_enum=True),
        nullable=False,
        default=StudySessionStatus.IN_PROGRESS,
    )
    current_stage: Mapped[StudyStage] = mapped_column(
        SqlEnum(StudyStage, name="study_stage", native_enum=True),
        nullable=False,
        default=StudyStage.INTRODUCTION,
    )
    current_item_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exercise_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["StudySessionItem"]] = relationship(
        back_populates="session",
        order_by="StudySessionItem.position",
        cascade="all, delete-orphan",
    )


class StudySessionItem(Base):
    __tablename__ = "study_session_items"
    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_study_session_items_position"),
        CheckConstraint(
            "(user_vocabulary_item_id IS NOT NULL AND irregular_verb_id IS NULL)"
            " OR (user_vocabulary_item_id IS NULL AND irregular_verb_id IS NOT NULL)",
            name="ck_study_session_items_exactly_one_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("study_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_vocabulary_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user_vocabulary_items.id", ondelete="RESTRICT")
    )
    irregular_verb_id: Mapped[int | None] = mapped_column(
        ForeignKey("irregular_verbs.id", ondelete="RESTRICT")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    session: Mapped[StudySession] = relationship(back_populates="items")
```

Создайте пустую таблицу `irregular_verbs` (id bigint PK) уже в этой миграции — FK валиден, seed
придёт на шаге 48. Частичный уникальный индекс ловит гонку двух `POST`: один получит unique
violation, сервис шага 45 вернёт существующую сессию. `ondelete="RESTRICT"` на карточках: удаление
слова из активной сессии в MVP запрещается в vocabulary-сервисе.

Подключите модели в `models_registry.py` и сгенерируйте миграцию:

```bash
cd backend
POSTGRES_HOST=localhost uv run alembic revision --autogenerate -m "add study sessions"
```

Откройте файл. Проверьте:

* enum-типы `study_session_kind`, `study_session_status`, `study_stage`;
* частичный уникальный индекс с `postgresql_where`;
* CHECK на `study_session_items`;
* в `downgrade()` явное `DROP TYPE` для трёх enum — Alembic часто забывает.

Примените и проверьте откат:

```bash
POSTGRES_HOST=localhost uv run alembic upgrade head
POSTGRES_HOST=localhost uv run alembic downgrade -1
POSTGRES_HOST=localhost uv run alembic upgrade head
```

### Проверка

```bash
cd infra
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\d study_sessions"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\d study_session_items"
docker compose exec postgres psql -U vocabulary -d vocabulary -c "\di *study_session*"
```

В `\d study_sessions` видны `kind`, `status`, `current_stage`, `current_item_index`,
`exercise_payload`, `started_at`, `completed_at`. Индекс `uq_study_sessions_one_active_per_user`
существует.

### Коммит

`feat(backend): add study session and session item models`

---

## Шаг 44. Отбор слов для занятия с тестами

### Цель

Чистая функция выбирает слова: сначала неизученные (`study_count = 0`), затем случайные ранее
изученные. Размер 5 / 10 / 15 / custom. В выборку попадают только пригодные к изучению карточки.

Алгоритм живёт отдельно от FastAPI и SQLAlchemy, чтобы его можно было тестировать списком
dataclass без БД. Репозиторий на шаге 45 только готовит список кандидатов.

### Файлы

```text
backend/app/study/selection.py
backend/tests/test_study_selection.py
```

### Кто считается пригодным к изучению

| `enrichment_status` | Перевод есть | Берём? |
| --- | --- | --- |
| `READY` | да | да |
| `READY` | нет | нет (битые данные, не учим молча) |
| `PARTIAL` | да | да — частичная деградация: нет audio/definition, но matching по переводу возможен |
| `PARTIAL` | нет | нет — matching и definition не из чего строить |
| `PENDING` | любой | нет — карточка ещё не готова |
| `ENRICHING` | любой | нет — идёт подготовка |
| `FAILED` | любой | нет — карточка непригодна; если перевод всё же есть, статус должен был стать `PARTIAL` |

«Перевод есть» — хотя бы одна `Translation` для `meaning_id` на родной язык пользователя.
Проверка делается при загрузке кандидатов (JOIN), а не внутри чистой функции: функция получает
уже отфильтрованный список.

`FAILED` не учим даже «на всякий случай». Иначе пользователь получит пустые упражнения, а статус
перестанет что-либо значить.

### Действия

`backend/app/study/selection.py`:

```python
from dataclasses import dataclass
from enum import StrEnum
from random import Random
from uuid import UUID

from app.vocabulary.models import EnrichmentStatus


class StudySelectionMode(StrEnum):
    RANDOM = "RANDOM"
    MANUAL = "MANUAL"


STUDY_SIZE_PRESETS: frozenset[int] = frozenset({5, 10, 15})
STUDY_SIZE_CUSTOM_MIN = 1
STUDY_SIZE_CUSTOM_MAX = 50


@dataclass(frozen=True, slots=True)
class SelectableVocabularyItem:
    id: UUID
    study_count: int


class StudySelectionError(Exception):
    pass


class StudySizeInvalidError(StudySelectionError):
    pass


class StudySelectionEmptyError(StudySelectionError):
    pass


class ManualSelectionInvalidError(StudySelectionError):
    pass


def validate_study_size(size: int) -> int:
    if size in STUDY_SIZE_PRESETS:
        return size
    if STUDY_SIZE_CUSTOM_MIN <= size <= STUDY_SIZE_CUSTOM_MAX:
        return size
    raise StudySizeInvalidError(f"unsupported study size: {size}")


def is_studiable(*, enrichment_status: EnrichmentStatus, has_translation: bool) -> bool:
    if not has_translation:
        return False
    return enrichment_status in {EnrichmentStatus.READY, EnrichmentStatus.PARTIAL}


def select_vocabulary_item_ids(
    candidates: list[SelectableVocabularyItem],
    *,
    size: int,
    mode: StudySelectionMode,
    manual_ids: list[UUID] | None = None,
    rng: Random,
) -> list[UUID]:
    size = validate_study_size(size)

    if mode is StudySelectionMode.MANUAL:
        return _select_manual(candidates, size=size, manual_ids=manual_ids or [])

    return _select_random_new_first(candidates, size=size, rng=rng)


def _select_manual(
    candidates: list[SelectableVocabularyItem],
    *,
    size: int,
    manual_ids: list[UUID],
) -> list[UUID]:
    if len(manual_ids) != size:
        raise ManualSelectionInvalidError("manual selection size must match requested size")
    if len(set(manual_ids)) != len(manual_ids):
        raise ManualSelectionInvalidError("manual selection contains duplicates")

    available_ids = {item.id for item in candidates}
    unknown_ids = [item_id for item_id in manual_ids if item_id not in available_ids]
    if unknown_ids:
        raise ManualSelectionInvalidError("manual selection contains items that cannot be studied")

    return list(manual_ids)


def _select_random_new_first(
    candidates: list[SelectableVocabularyItem],
    *,
    size: int,
    rng: Random,
) -> list[UUID]:
    if not candidates:
        raise StudySelectionEmptyError("no studiable vocabulary items")

    new_items = [item for item in candidates if item.study_count == 0]
    studied_items = [item for item in candidates if item.study_count > 0]

    rng.shuffle(new_items)
    rng.shuffle(studied_items)

    ordered = new_items + studied_items
    selected = ordered[: min(size, len(ordered))]
    return [item.id for item in selected]
```

Почему `rng` передаётся снаружи: в тестах фиксируем seed и проверяем порядок, в сервисе передаём
`Random()`. Глобальный `random.shuffle` сделал бы тесты флапающими.

Почему ручной режим требует `size == len(manual_ids)`: UI показывает пресет 5/10/15, пользователь
отмечает ровно столько карточек. Если отмечено меньше — кнопка «Начать» неактивна на фронте;
backend всё равно проверяет, клиенту нельзя доверять.

Если доступно 8 карточек, а запрошено 15 — random-режим возвращает 8, не ошибку. Пустой список
кандидатов — ошибка: занятие из нуля слов нельзя пройти.

`backend/tests/test_study_selection.py`:

```python
from random import Random
from uuid import uuid4

import pytest

from app.study.selection import (
    ManualSelectionInvalidError,
    SelectableVocabularyItem,
    StudySelectionEmptyError,
    StudySelectionMode,
    StudySizeInvalidError,
    is_studiable,
    select_vocabulary_item_ids,
    validate_study_size,
)
from app.vocabulary.models import EnrichmentStatus


def _item(study_count: int) -> SelectableVocabularyItem:
    return SelectableVocabularyItem(id=uuid4(), study_count=study_count)


def test_ready_with_translation_is_studiable() -> None:
    assert is_studiable(enrichment_status=EnrichmentStatus.READY, has_translation=True)


def test_partial_with_translation_is_studiable() -> None:
    assert is_studiable(enrichment_status=EnrichmentStatus.PARTIAL, has_translation=True)


def test_partial_without_translation_is_not_studiable() -> None:
    assert not is_studiable(enrichment_status=EnrichmentStatus.PARTIAL, has_translation=False)


def test_pending_enriching_failed_are_not_studiable() -> None:
    for status in (
        EnrichmentStatus.PENDING,
        EnrichmentStatus.ENRICHING,
        EnrichmentStatus.FAILED,
    ):
        assert not is_studiable(enrichment_status=status, has_translation=True)


def test_new_items_are_taken_before_studied() -> None:
    new_a = _item(0)
    new_b = _item(0)
    old_a = _item(3)
    old_b = _item(1)
    selected = select_vocabulary_item_ids(
        [old_a, new_a, old_b, new_b],
        size=2,
        mode=StudySelectionMode.RANDOM,
        rng=Random(1),
    )
    assert set(selected) == {new_a.id, new_b.id}


def test_studied_items_fill_remaining_slots() -> None:
    new_a = _item(0)
    old_a = _item(2)
    old_b = _item(4)
    selected = select_vocabulary_item_ids(
        [old_a, new_a, old_b],
        size=5,
        mode=StudySelectionMode.RANDOM,
        rng=Random(7),
    )
    assert selected[0] == new_a.id
    assert set(selected[1:]) == {old_a.id, old_b.id}
    assert len(selected) == 3


def test_selection_is_deterministic_with_seed() -> None:
    items = [_item(0) for _ in range(10)]
    first = select_vocabulary_item_ids(
        items, size=5, mode=StudySelectionMode.RANDOM, rng=Random(42)
    )
    second = select_vocabulary_item_ids(
        items, size=5, mode=StudySelectionMode.RANDOM, rng=Random(42)
    )
    assert first == second


def test_empty_candidates_raise() -> None:
    with pytest.raises(StudySelectionEmptyError):
        select_vocabulary_item_ids(
            [], size=5, mode=StudySelectionMode.RANDOM, rng=Random()
        )


def test_manual_keeps_given_order() -> None:
    items = [_item(0) for _ in range(5)]
    manual_ids = [items[2].id, items[0].id, items[4].id]
    selected = select_vocabulary_item_ids(
        items,
        size=3,
        mode=StudySelectionMode.MANUAL,
        manual_ids=manual_ids,
        rng=Random(),
    )
    assert selected == manual_ids


def test_manual_rejects_unknown_or_duplicate() -> None:
    items = [_item(0) for _ in range(2)]
    with pytest.raises(ManualSelectionInvalidError):
        select_vocabulary_item_ids(
            items,
            size=2,
            mode=StudySelectionMode.MANUAL,
            manual_ids=[items[0].id, uuid4()],
            rng=Random(),
        )
    with pytest.raises(ManualSelectionInvalidError):
        select_vocabulary_item_ids(
            items,
            size=2,
            mode=StudySelectionMode.MANUAL,
            manual_ids=[items[0].id, items[0].id],
            rng=Random(),
        )


def test_custom_size_bounds() -> None:
    assert validate_study_size(8) == 8
    with pytest.raises(StudySizeInvalidError):
        validate_study_size(0)
    with pytest.raises(StudySizeInvalidError):
        validate_study_size(51)
```

### Проверка

```bash
cd backend
uv run pytest tests/test_study_selection.py -v
```

Все тесты зелёные. Особенно `test_new_items_are_taken_before_studied`: если он красный, в отбор
попали изученные раньше новых — это сломает смысл кнопки «Случайно».

### Коммит

`feat(backend): add new-first study item selection`

---

## Шаг 45. Создание сессии: одна активная, иначе вернуть существующую

### Цель

`POST /api/v1/study-sessions` создаёт занятие или возвращает незавершённое. Вторую активную сессию
создать нельзя.

### Файлы

```text
backend/app/study/schemas.py
backend/app/study/errors.py
backend/app/study/repository.py
backend/app/study/exercise_payload.py     заготовка, заполняется на шаге 46
backend/app/study/service.py
backend/app/study/router.py
backend/app/main.py                       include_router
backend/tests/test_study_session_create.py
```

Тела запросов и ответов — [08-api-reference.md](08-api-reference.md), раздел Study. Здесь —
поведение.

### Поведение POST

1. Если у пользователя есть сессия `IN_PROGRESS` — вернуть её (тот же JSON, что у `GET`), статус
   HTTP 200. Параметры нового запроса игнорируются: нельзя тихо подменить набор слов.
2. Если активной нет — отобрать слова, сгенерировать payload, записать сессию и items, вернуть 201.
3. Unique violation на частичном индексе → ещё раз прочитать активную и вернуть её (гонка двух POST).

Фронт на экране настройки не должен слать POST вслепую: сначала `GET /api/v1/study-sessions/active`.
Но POST всё равно идемпотентен относительно «одна активная», потому что Mini App могут открыть
дважды.

### Действия

`backend/app/study/errors.py`:

```python
from app.common.errors import ApplicationError, EntityNotFoundError, ValidationFailedError


class StudySessionNotFoundError(EntityNotFoundError):
    pass


class StudySessionNotActiveError(ApplicationError):
    pass


class StudyCollectionNotFoundError(EntityNotFoundError):
    pass


class StudyPayloadInvalidError(ValidationFailedError):
    pass
```

Репозиторий загружает кандидатов одним запросом: карточки темы пользователя с переводом на родной
язык и статусом `READY` или `PARTIAL`. Не тащите N+1 по `Meaning` / `Translation`.

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.collections.models import CollectionItem
from app.lexicon.models import Meaning, Translation
from app.vocabulary.models import EnrichmentStatus, UserVocabularyItem


async def list_studiable_items_in_collection(
    self,
    *,
    user_id: UUID,
    collection_id: UUID,
    native_language_id: int,
) -> list[UserVocabularyItem]:
    statement = (
        select(UserVocabularyItem)
        .join(CollectionItem, CollectionItem.user_vocabulary_item_id == UserVocabularyItem.id)
        .join(Meaning, Meaning.id == UserVocabularyItem.meaning_id)
        .join(Translation, Translation.meaning_id == Meaning.id)
        .where(
            CollectionItem.collection_id == collection_id,
            UserVocabularyItem.user_id == user_id,
            UserVocabularyItem.enrichment_status.in_(
                (EnrichmentStatus.READY, EnrichmentStatus.PARTIAL)
            ),
            Translation.language_id == native_language_id,
        )
        .options(
            selectinload(UserVocabularyItem.meaning).selectinload(Meaning.lexeme),
            selectinload(UserVocabularyItem.meaning).selectinload(Meaning.translations),
            selectinload(UserVocabularyItem.meaning).selectinload(Meaning.contents),
        )
        .distinct()
    )
    result = await self._session.execute(statement)
    return list(result.scalars().unique().all())
```

Имена связей (`meaning`, `lexeme`, `contents`) возьмите из моделей недели 2. Если там иначе —
подстройте `selectinload`, не копируйте вслепую.

Сервис создания:

```python
from random import Random
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.study.exercise_payload import build_vocabulary_exercise_payload
from app.study.models import StudySession, StudySessionItem, StudySessionKind, StudySessionStatus
from app.study.repository import StudySessionRepository
from app.study.schemas import StudySessionCreate
from app.study.selection import (
    SelectableVocabularyItem,
    StudySelectionMode,
    select_vocabulary_item_ids,
)
from app.users.models import User


class StudySessionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = StudySessionRepository(session)

    async def create_or_return_active(
        self,
        user: User,
        request: StudySessionCreate,
    ) -> StudySession:
        existing = await self._repository.find_active_for_user(user.id)
        if existing is not None:
            return existing

        if user.native_language_id is None:
            raise StudyPayloadInvalidError("onboarding is not completed")

        collection = await self._repository.get_user_collection(user.id, request.collection_id)
        if collection is None:
            raise StudyCollectionNotFoundError()

        candidates = await self._repository.list_studiable_items_in_collection(
            user_id=user.id,
            collection_id=request.collection_id,
            native_language_id=user.native_language_id,
        )
        selectable = [
            SelectableVocabularyItem(id=item.id, study_count=item.study_count)
            for item in candidates
        ]
        selected_ids = select_vocabulary_item_ids(
            selectable,
            size=request.size,
            mode=StudySelectionMode(request.mode),
            manual_ids=request.vocabulary_item_ids,
            rng=Random(),
        )
        items_by_id = {item.id: item for item in candidates}
        ordered_items = [items_by_id[item_id] for item_id in selected_ids]
        payload = build_vocabulary_exercise_payload(ordered_items, user)

        study_session = StudySession(
            user_id=user.id,
            collection_id=collection.id,
            kind=StudySessionKind.VOCABULARY,
            exercise_payload=payload,
        )
        for position, item in enumerate(ordered_items):
            study_session.items.append(
                StudySessionItem(
                    user_vocabulary_item_id=item.id,
                    position=position,
                )
            )
        self._session.add(study_session)

        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self._repository.find_active_for_user(user.id)
            if existing is None:
                raise
            return existing

        await self._session.refresh(study_session)
        return study_session
```

На этом шаге `build_vocabulary_exercise_payload` может вернуть минимальный каркас:
`{"kind": "VOCABULARY", "items": [...], "stages": [...]}` без shuffle — шаг 46 допишет задания.
Сессию создать нужно уже сейчас, чтобы контракт POST существовал.

Роутер тонкий: ловит доменные ошибки, не пишет SQL. Подключение:

```python
app.include_router(study_router, prefix=settings.api_base_path)
```

Эндпоинты этого шага:

* `POST /api/v1/study-sessions`
* `GET /api/v1/study-sessions/active` — 404, если нет; нужен фронту до POST и для баннера restore

Полные схемы `StudySessionCreate` / `StudySessionResponse` — в 08. Поля create: `collection_id`,
`size`, `mode` (`RANDOM` | `MANUAL`), `vocabulary_item_ids` (обязательны при `MANUAL`).

Тест создания: два вызова POST подряд возвращают один `id`; ручной набор неизвестного id — 422;
пустая тема — 422.

### Проверка

```bash
cd backend
uv run pytest tests/test_study_session_create.py -v
```

Два `POST` подряд (size 5, затем size 10) — один `id`, статус `IN_PROGRESS`, размер не сменился.
В `study_sessions` одна строка.

### Коммит

`feat(backend): create study session or return the active one`

---

## Шаг 46. GET сессии с готовыми упражнениями

### Цель

`GET /api/v1/study-sessions/{id}` возвращает полный payload: перемешанные пары matching, предложение
с пропуском, задание на definition. Повторный GET после рестарта процесса даёт **тот же** JSON.

### Почему упражнения собирает сервер

Клиентский shuffle выглядит дешевле и «античитовее». Для MVP это ошибка. Restore обязателен: Mini App
убивается при закрытии Telegram. Если пары matching и пропуск в предложении рождаются на клиенте,
после открытия пользователь увидит другое задание — это потеря прогресса при том же этапе.

Античит почти ничего не даёт: баллов нет, перевод уже показан на знакомстве, проверка ответа
клиентская. Цена клиентского shuffle — сломанный restore. Снимок пишется один раз в
`exercise_payload` и не пересчитывается. `PATCH` меняет только курсор (`current_stage`,
`current_item_index`).

### Файлы

```text
backend/app/study/exercise_payload.py
backend/app/study/answer_blank.py
backend/tests/test_exercise_payload.py
правка study/service.py, schemas.py, router.py
```

### Форма payload

Не дублируйте поля карточки, которых нет в 08. Минимальная структура, которую ждут шаги 50–56:

```text
kind: VOCABULARY | IRREGULAR_VERBS
stages: упорядоченный список этапов этой сессии
matching: { left: [{itemId, text}], right: [{itemId, text}] }   только для VOCABULARY
items: [
  {
    itemId,
    position,
    lexemeType: word | phrase,
    introduction: { text, ipa, audioUrl, translation, definition, example },
    sentence: { prompt, answer } | null,          null у phrase
    definitionExercise: { prompt, answer } | null
  }
]
wordList: [text]   полный список, один на сессию, для этапов 3 и 4
```

Для `IRREGULAR_VERBS` matching нет, у item другие упражнения — шаг 49.

### Действия

Вырезание ответа из примера: берём `MeaningContent.example` уровня CEFR пользователя. Ищем первое
вхождение лексемы без учёта регистра, заменяем на `_____`. Если вхождения нет (AI-пример не содержит
слово — редкий брак) — fallback: `"{example} ({text})"`, answer = текст лексемы, чтобы этап не
ломался. Не генерируйте новый пример на лету: это другой промпт и другая цена.

```python
import re


def blank_example(example: str, lexeme_text: str) -> tuple[str, str]:
    pattern = re.compile(re.escape(lexeme_text), re.IGNORECASE)
    if pattern.search(example) is None:
        return example, lexeme_text
    prompt = pattern.sub("_____", example, count=1)
    return prompt, lexeme_text
```

Matching: левая колонка — английские единицы в порядке `position`, правая — переводы, перемешанные
через `rng.shuffle`. В payload хранятся оба массива уже в том виде, в каком их рисует UI. Клиент
не перемешивает повторно.

Definition prompt — `MeaningContent.definition`. Если definition нет (`PARTIAL` без AI) — это слово
всё равно входит в matching и introduction; на этапе definition показываем перевод как запасной
prompt. Честнее пройти этап, чем выкидывать слово из уже начатой сессии.

Порядок `stages` для обычной пачки:

* есть хотя бы одно `word` → `INTRODUCTION`, `MATCHING`, `SENTENCE`, `DEFINITION`;
* все `phrase` → `INTRODUCTION`, `MATCHING`, `DEFINITION`.

Смешанная пачка: этап `SENTENCE` есть, но в нём только word-элементы. Store на шаге 54 итерирует
`items.filter(i => i.sentence !== null)`.

GET чужой сессии — `StudySessionNotFoundError` (как 404, без «это не ваше»). GET завершённой —
разрешён, фронт покажет экран «занятие завершено», не продолжит этапы.

Допишите сборку payload и покройте тестом: два вызова `build_vocabulary_exercise_payload` с одним
`Random(seed)` дают одинаковый matching; phrase получает `sentence is None`; stages без `SENTENCE`,
если слов нет.

### Проверка

```bash
uv run pytest tests/test_exercise_payload.py tests/test_study_session_create.py -v
```

Создайте сессию, сохраните ответ GET, перезапустите backend, повторите GET — `matching.right`
совпадает побайтно. Это главная проверка шага.

### Коммит

`feat(backend): generate and persist study exercise payload`

---

## Шаг 47. Прогресс PATCH и завершение POST

### Цель

Клиент сохраняет этап и индекс слова. По завершении у всех карточек сессии растут `study_count` и
ставится `last_studied_at`. Этапы не теряются.

### Файлы

```text
backend/app/study/service.py      методы save_progress, complete
backend/app/study/router.py
backend/tests/test_study_progress.py
```

Контракт PATCH/POST — в 08.

### Действия

PATCH `/api/v1/study-sessions/{id}/progress`:

```python
from datetime import UTC, datetime

from app.study.models import StudySessionStatus


async def save_progress(
    self,
    user_id: UUID,
    session_id: UUID,
    stage: StudyStage,
    item_index: int,
) -> StudySession:
    study_session = await self._require_own_active(user_id, session_id)
    stages = study_session.exercise_payload["stages"]
    if stage.value not in stages:
        raise StudyPayloadInvalidError("stage is not part of this session")
    if item_index < 0:
        raise StudyPayloadInvalidError("item index is negative")

    study_session.current_stage = stage
    study_session.current_item_index = item_index
    await self._session.commit()
    return study_session
```

Не требуйте «только вперёд». Пользователь может упереться в баг UI и дернуть PATCH дважды с тем же
индексом. Идемпотентность важнее античита. Проверяйте только: сессия своя, `IN_PROGRESS`, этап есть
в payload.

POST `/api/v1/study-sessions/{id}/complete`:

* статус `COMPLETED`, `completed_at = now(UTC)`;
* для каждого `user_vocabulary_item_id` в items: `study_count += 1`, `last_studied_at = now`;
* повторный complete — ошибка `StudySessionNotActiveError` (409);
* глагольная сессия шага 49 не трогает `UserVocabularyItem` — items там без этих id;
* одна транзакция на сервис, `commit()` один раз.

Инкремент через SQL, не цикл с dirty-read:

```python
from sqlalchemy import update

from app.vocabulary.models import UserVocabularyItem


item_ids = [
    session_item.user_vocabulary_item_id
    for session_item in study_session.items
    if session_item.user_vocabulary_item_id is not None
]
if item_ids:
    await self._session.execute(
        update(UserVocabularyItem)
        .where(UserVocabularyItem.id.in_(item_ids))
        .values(
            study_count=UserVocabularyItem.study_count + 1,
            last_studied_at=datetime.now(UTC),
        )
    )
```

После complete частичный уникальный индекс освобождается — можно стартовать следующее занятие.

Тесты: PATCH меняет `current_stage`; complete увеличивает `study_count` с 0 до 1; второй complete
падает; complete не меняет payload.

### Проверка

```bash
uv run pytest tests/test_study_progress.py -v
```

Вручную: PATCH на `SENTENCE` / index 2, `GET` отдаёт те же значения. Complete — в БД
`status=COMPLETED`, у карточек `study_count=1`.

### Коммит

`feat(backend): persist study progress and complete session`

---

## Шаг 48. Модель `IrregularVerb` и seed ~15–20 глаголов

### Цель

В БД справочник неправильных глаголов с тремя формами, переводом и отдельным аудио на каждую форму.
MVP-набор небольшой; полный школьный список — после MVP.

### Файлы

```text
backend/app/irregular_verbs/__init__.py
backend/app/irregular_verbs/models.py
backend/app/irregular_verbs/seed.py
правка models_registry.py
alembic-миграция (таблица, если не создали на шаге 43, + seed data)
```

Схема — в 07, раздел `IrregularVerb`. Не размазывайте полный CREATE TABLE здесь.

### Действия

Модель:

```python
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import Base


class IrregularVerb(Base):
    __tablename__ = "irregular_verbs"
    __table_args__ = (UniqueConstraint("base_lexeme_id", name="uq_irregular_verbs_base_lexeme"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    base_lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexemes.id", ondelete="RESTRICT"))
    past_simple: Mapped[str] = mapped_column(String(80), nullable=False)
    past_participle: Mapped[str] = mapped_column(String(80), nullable=False)
    past_simple_alt: Mapped[str | None] = mapped_column(String(80))
    base_audio_url: Mapped[str | None] = mapped_column(String(512))
    past_audio_url: Mapped[str | None] = mapped_column(String(512))
    participle_audio_url: Mapped[str | None] = mapped_column(String(512))
    translation: Mapped[str] = mapped_column(String(120), nullable=False)
```

`past_simple_alt` — для `be` (`was` / `were`). Проверка ответа на шаге 56 принимает любую из форм.
Не пишите `was/were` одной строкой как единственный правильный ответ.

`base_lexeme_id` связывает глагол с общим лексиконом: IPA и канонический текст берутся оттуда.
Три URL аудио — отдельные файлы, не один трек. На MVP URL могут быть `NULL`: карточка живая,
кнопка аудио скрывается, как на обычном слове в `PARTIAL`.

Seed ~18 частотных глаголов. Полный школьный список (200+) — в `docs/post-mvp.md`, не в MVP.

```text
be was/were been; go went gone; do did done; have had had
say said said; make made made; know knew known; think thought thought
take took taken; see saw seen; come came come; get got got
give gave given; find found found; tell told told; become became become
leave left left; feel felt felt; put put put; bring brought brought
```

`be`: `past_simple=was`, `past_simple_alt=were`. `get`: `got/got`, не `gotten`. Seed идемпотентен
(`ON CONFLICT DO NOTHING`), лексемы создаются при отсутствии, без enrichment и без
`UserVocabularyItem`. Аудио URL на MVP могут быть NULL; TTS нет.

Миграция data-seed отдельным ревижном после схемы, как языки на шаге 13. `downgrade` удаляет
строки `irregular_verbs`, лексемы не трогает (они общие).

### Проверка

```bash
POSTGRES_HOST=localhost uv run alembic upgrade head
docker compose exec postgres psql -U vocabulary -d vocabulary -c \
  "select count(*) from irregular_verbs;"
docker compose exec postgres psql -U vocabulary -d vocabulary -c \
  "select l.text, v.past_simple, v.past_simple_alt, v.past_participle, v.translation
   from irregular_verbs v join lexemes l on l.id = v.base_lexeme_id order by v.id;"
```

Count ≥ 15. У `be` заполнен `past_simple_alt`. Три колонки audio существуют.

### Коммит

`feat(backend): add irregular verbs reference and mvp seed`

---

## Шаг 49. Системная тема «Неправильные глаголы» и API глагольной сессии

### Цель

В списке тем у каждого пользователя видна системная тема. Старт занятия по ней идёт другим
эндпоинтом и другим `kind`. `user_id` у темы `NULL`, `is_system=true`.

### Файлы

```text
backend/app/collections/models.py     поле system_key, если его не было на неделе 2
миграция collections.system_key
backend/app/irregular_verbs/seed.py   создание системной Collection
backend/app/study/service.py          start_irregular_verb_session
backend/app/study/router.py
backend/app/study/exercise_payload.py  build_irregular_verb_payload
```

### Действия

Системную тему нельзя идентифицировать по русскому названию — его когда-нибудь переименуют.
Добавьте `system_key: Mapped[str | None]` с unique. Значение `irregular_verbs`.

Правила системной темы:

* `user_id IS NULL`, `is_system IS TRUE`;
* нет `CollectionItem` на `UserVocabularyItem` — состав темы это таблица `irregular_verbs`;
* обычный CRUD недели 2 не даёт её удалить, переименовать или добавить туда слово пользователя
  (проверка `is_system` в collections-сервисе);
* `GET /collections` отдаёт её вместе с личными, помеченную флагом.

Эндпоинт старта — отдельный, чтобы не смешивать ручной выбор карточек с глаголами:

`POST /api/v1/study-sessions/irregular-verbs`

Тело: `{ "size": 5 | 10 | 15 | custom }`. Mode только random: ручной выбор глаголов в MVP не нужен.
Поведение активной сессии то же, что на шаге 45: если есть любая `IN_PROGRESS` (даже словарная) —
вернуть её, не создавать глагольную. Одна активная на пользователя, без исключений.

Отбор глаголов: случайные `size` штук из справочника. `new-first` по `study_count` здесь нет —
у справочника нет пользовательского счётчика в MVP. Не изобретайте его.

Payload `kind=IRREGULAR_VERBS`:

```text
stages: INTRODUCTION, VERB_CONJUGATION, VERB_FORM_PROMPT
items: [
  {
    itemId,              id строки irregular_verbs
    position,
    introduction: {
      base, pastSimple, pastParticiple, translation,
      baseAudioUrl, pastAudioUrl, participleAudioUrl, ipa
    },
    conjugation: { promptBase, pastSimpleAnswers, pastParticipleAnswers },
    formPrompts: [
      { kind: PAST_SIMPLE, prompt, answers },
      { kind: PAST_PARTICIPLE, prompt, answers }
    ]
  }
]
```

`pastSimpleAnswers` для `be` — `["was", "were"]`. Prompt conjugation на фронте: `go → ? → ?`.
Prompt form: `Past Simple of "go"` / `Past Participle of "go"` — строки собирает сервер, фронт их
не конкатенирует (иначе restore и локализация разъедутся).

GET тот же, что для словарной сессии: фронт смотрит на `kind` и включает другой набор компонентов.

Тест: POST irregular при активной vocabulary-сессии возвращает vocabulary-сессию; после complete
можно стартовать глаголы; payload без `matching` и без `SENTENCE`.

### Проверка

```bash
curl -s http://localhost:8080/api/v1/collections -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool
```

В списке есть «Неправильные глаголы», `is_system: true`.

```bash
curl -s -X POST http://localhost:8080/api/v1/study-sessions/irregular-verbs \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"size":5}' | python3 -m json.tool
```

`kind` = `IRREGULAR_VERBS`, `stages` без `MATCHING` и `SENTENCE`, у каждого item три формы.

### Коммит

`feat(backend): add system irregular verbs collection and session api`

---

## Шаг 50. Frontend: `StudySessionStore`

### Цель

Состояние занятия живёт в одном store на signals: сессия, этап, индекс, попытки, выбранные пары,
загрузка. Компоненты этапов не ходят в HTTP и не дублируют переходы.

NgRx не подключать. RxJS — только на вызовах API (`firstValueFrom` / `subscribe` в store).

### Файлы

```text
frontend/src/app/features/study/study-api.ts
frontend/src/app/features/study/study-session.types.ts
frontend/src/app/features/study/study-session-store.ts
frontend/src/app/features/study/study-answer.ts
frontend/src/app/features/study/study-answer.spec.ts
frontend/src/app/features/study/study-session-store.spec.ts
```

Типы ответа зеркальте контракт 08, не придумывайте вторую модель «для UI», пока поля один в один.

### Действия

`study-answer.ts` — чистая строгая проверка, без store:

```typescript
export function normalizeStudyAnswer(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toLowerCase();
}

export function answersMatch(expected: string, actual: string): boolean {
  return normalizeStudyAnswer(expected) === normalizeStudyAnswer(actual);
}

export function answersMatchAny(expected: readonly string[], actual: string): boolean {
  const normalized = normalizeStudyAnswer(actual);
  return expected.some((item) => normalizeStudyAnswer(item) === normalized);
}

export const MAX_STUDY_ATTEMPTS = 3;
```

`study-api.ts` знает только URL:

```typescript
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  IrregularVerbSessionCreate,
  StudyProgressUpdate,
  StudySessionCreate,
  StudySessionResponse,
} from './study-session.types';

@Injectable({ providedIn: 'root' })
export class StudyApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/study-sessions`;

  createSession(body: StudySessionCreate): Observable<StudySessionResponse> {
    return this.http.post<StudySessionResponse>(this.baseUrl, body);
  }

  createIrregularVerbSession(
    body: IrregularVerbSessionCreate,
  ): Observable<StudySessionResponse> {
    return this.http.post<StudySessionResponse>(`${this.baseUrl}/irregular-verbs`, body);
  }

  getActiveSession(): Observable<StudySessionResponse> {
    return this.http.get<StudySessionResponse>(`${this.baseUrl}/active`);
  }

  getSession(sessionId: string): Observable<StudySessionResponse> {
    return this.http.get<StudySessionResponse>(`${this.baseUrl}/${sessionId}`);
  }

  saveProgress(
    sessionId: string,
    body: StudyProgressUpdate,
  ): Observable<StudySessionResponse> {
    return this.http.patch<StudySessionResponse>(`${this.baseUrl}/${sessionId}/progress`, body);
  }

  completeSession(sessionId: string): Observable<StudySessionResponse> {
    return this.http.post<StudySessionResponse>(`${this.baseUrl}/${sessionId}/complete`, {});
  }
}
```

Store — сердце недели. Провайдьте его на `StudyPage`, не в `root`:

```typescript
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '../../core/api/api-error';
import { MAX_STUDY_ATTEMPTS, answersMatch, answersMatchAny } from './study-answer';
import { StudyApi } from './study-api';
import {
  MatchingOption,
  StudySessionItemPayload,
  StudySessionResponse,
  StudyStage,
} from './study-session.types';

@Injectable()
export class StudySessionStore {
  private readonly studyApi = inject(StudyApi);

  private readonly sessionState = signal<StudySessionResponse | null>(null);
  private readonly currentStageState = signal<StudyStage>('INTRODUCTION');
  private readonly currentItemIndexState = signal(0);
  private readonly attemptsState = signal(0);
  private readonly selectedLeftIdState = signal<string | null>(null);
  private readonly selectedRightIdState = signal<string | null>(null);
  private readonly matchedItemIdsState = signal<readonly string[]>([]);
  private readonly loadingState = signal(false);
  private readonly errorState = signal<ApiError | null>(null);
  private readonly answerRevealedState = signal(false);
  private readonly translationRevealedState = signal(false);

  readonly session = this.sessionState.asReadonly();
  readonly currentStage = this.currentStageState.asReadonly();
  readonly currentItemIndex = this.currentItemIndexState.asReadonly();
  readonly attempts = this.attemptsState.asReadonly();
  readonly selectedLeftId = this.selectedLeftIdState.asReadonly();
  readonly selectedRightId = this.selectedRightIdState.asReadonly();
  readonly matchedItemIds = this.matchedItemIdsState.asReadonly();
  readonly loading = this.loadingState.asReadonly();
  readonly error = this.errorState.asReadonly();
  readonly answerRevealed = this.answerRevealedState.asReadonly();
  readonly translationRevealed = this.translationRevealedState.asReadonly();

  readonly items = computed(() => this.sessionState()?.exercise.payload.items ?? []);
  readonly stages = computed(() => this.sessionState()?.exercise.payload.stages ?? []);
  readonly matching = computed(() => this.sessionState()?.exercise.payload.matching ?? null);
  readonly wordList = computed(() => this.sessionState()?.exercise.payload.wordList ?? []);

  readonly stageItems = computed((): readonly StudySessionItemPayload[] => {
    const stage = this.currentStageState();
    const items = this.items();
    if (stage === 'SENTENCE') {
      return items.filter((item) => item.sentence !== null);
    }
    return items;
  });

  readonly currentItem = computed((): StudySessionItemPayload | null => {
    return this.stageItems()[this.currentItemIndexState()] ?? null;
  });

  readonly matchingComplete = computed(() => {
    const matching = this.matching();
    if (matching === null) {
      return false;
    }
    return this.matchedItemIdsState().length === matching.left.length;
  });

  readonly canRevealAnswer = computed(
    () => this.attemptsState() >= MAX_STUDY_ATTEMPTS || this.answerRevealedState(),
  );

  async load(sessionId: string): Promise<void> {
    this.loadingState.set(true);
    this.errorState.set(null);
    try {
      const session = await firstValueFrom(this.studyApi.getSession(sessionId));
      this.hydrate(session);
    } catch (error: unknown) {
      this.errorState.set(toApiError(error));
    } finally {
      this.loadingState.set(false);
    }
  }

  revealTranslation(): void {
    this.translationRevealedState.set(true);
  }

  selectMatchingOption(column: 'left' | 'right', option: MatchingOption): void {
    if (this.matchedItemIdsState().includes(option.itemId)) {
      return;
    }
    if (column === 'left') {
      this.selectedLeftIdState.set(option.itemId);
    } else {
      this.selectedRightIdState.set(option.itemId);
    }
    this.tryCompletePair();
  }

  submitTypedAnswer(actual: string): 'correct' | 'retry' | 'revealed' {
    const item = this.currentItem();
    if (item === null || this.answerRevealedState()) {
      return 'revealed';
    }
    const expected = this.expectedAnswers(item);
    if (answersMatchAny(expected, actual)) {
      return 'correct';
    }
    const nextAttempts = this.attemptsState() + 1;
    this.attemptsState.set(nextAttempts);
    if (nextAttempts >= MAX_STUDY_ATTEMPTS) {
      this.answerRevealedState.set(true);
      return 'revealed';
    }
    return 'retry';
  }

  async advanceAfterCorrectOrReveal(): Promise<void> {
    const items = this.stageItems();
    const index = this.currentItemIndexState();
    if (index + 1 < items.length) {
      await this.persistCursor(this.currentStageState(), index + 1);
      this.resetItemUi();
      return;
    }
    await this.advanceStage();
  }

  async completeMatchingAndAdvance(): Promise<void> {
    if (!this.matchingComplete()) {
      return;
    }
    await this.advanceStage();
  }

  private async advanceStage(): Promise<void> {
    const stages = this.stages();
    const current = this.currentStageState();
    const nextIndex = stages.indexOf(current) + 1;
    if (nextIndex >= stages.length) {
      await this.complete();
      return;
    }
    await this.persistCursor(stages[nextIndex], 0);
    this.resetItemUi();
    this.matchedItemIdsState.set([]);
    this.selectedLeftIdState.set(null);
    this.selectedRightIdState.set(null);
  }

  private async complete(): Promise<void> {
    const session = this.sessionState();
    if (session === null) {
      return;
    }
    const completed = await firstValueFrom(this.studyApi.completeSession(session.id));
    this.hydrate(completed);
  }

  private hydrate(session: StudySessionResponse): void {
    this.sessionState.set(session);
    this.currentStageState.set(session.currentStage);
    this.currentItemIndexState.set(session.currentItemIndex);
    this.resetItemUi();
    this.matchedItemIdsState.set([]);
  }

  private resetItemUi(): void {
    this.attemptsState.set(0);
    this.answerRevealedState.set(false);
    this.translationRevealedState.set(false);
  }

  private tryCompletePair(): void {
    const leftId = this.selectedLeftIdState();
    const rightId = this.selectedRightIdState();
    if (leftId === null || rightId === null) {
      return;
    }
    if (leftId === rightId) {
      this.matchedItemIdsState.update((ids) => [...ids, leftId]);
    }
    this.selectedLeftIdState.set(null);
    this.selectedRightIdState.set(null);
  }

  private expectedAnswers(item: StudySessionItemPayload): readonly string[] {
    const stage = this.currentStageState();
    if (stage === 'SENTENCE' && item.sentence) {
      return [item.sentence.answer];
    }
    if (stage === 'DEFINITION' && item.definitionExercise) {
      return [item.definitionExercise.answer];
    }
    if (stage === 'VERB_CONJUGATION' && item.conjugation) {
      return item.conjugation.pastSimpleAnswers;
    }
    if (stage === 'VERB_FORM_PROMPT' && item.formPrompts) {
      const prompt = item.formPrompts[this.formPromptIndex()];
      return prompt?.answers ?? [];
    }
    return [];
  }

  private formPromptIndex(): number {
    return this.currentItemIndexState() % 2;
  }

  private async persistCursor(stage: StudyStage, itemIndex: number): Promise<void> {
    const session = this.sessionState();
    if (session === null) {
      return;
    }
    this.currentStageState.set(stage);
    this.currentItemIndexState.set(itemIndex);
    const saved = await firstValueFrom(
      this.studyApi.saveProgress(session.id, {
        currentStage: stage,
        currentItemIndex: itemIndex,
      }),
    );
    this.sessionState.set(saved);
  }
}
```

Имена полей payload (`exercise.payload`, `currentStage`) выровняйте с 08, когда будете писать типы.
Смысл store не меняется: hydrate из ответа сервера, UI-попытки локально, курсор — на сервер.

`formPromptIndex` выше — заглушка: на шаге 56 замените на явный курсор внутри `formPrompts`
(два задания на глагол). Не размножайте `% 2` в компонентах.

Тесты store на этом шаге — обязательное ядро. Остальные UI-тесты можно добить на шаге 63, но
переходы, 3 попытки, skip phrase, matching и hydrate-restore пишутся **здесь**, иначе неделя 4
будет чинить поведение, которое уже уехало в компоненты.

Минимальный `study-session-store.spec.ts`:

* три неверных `submitTypedAnswer` → `answerRevealed() === true`;
* `stageItems` на `SENTENCE` отфильтрован по `sentence !== null`;
* matching: одинаковый `itemId` попадает в `matchedItemIds`, разный — нет;
* `hydrate` с `DEFINITION` / index 2 выставляет те же значения.

`StudyApi` в TestBed — stub с `vi.fn()`. Имена полей ответа выровняйте с 08, лишнюю обёртку
`exercise` не добавляйте.

### Проверка

```bash
cd frontend
npx tsc --noEmit
npm test -- --watch=false src/app/features/study/study-answer.spec.ts
npm test -- --watch=false src/app/features/study/study-session-store.spec.ts
```

### Коммит

`feat(frontend): add study session store with signals`

---

## Шаг 51. Экран настройки занятия

### Цель

Из темы пользователь выбирает количество (5 / 10 / 15 / своё) и режим: случайно или вручную.
Старт создаёт сессию и открывает `/study/:sessionId`.

### Файлы

```text
frontend/src/app/features/study/study-setup-page.ts
frontend/src/app/features/study/study-setup-page.html
frontend/src/app/features/study/study-setup-page.scss
frontend/src/app/features/study/study-size.ts
правка collection-page — кнопка «Начать занятие»
правка app.routes.ts
```

### Действия

Маршруты:

```typescript
{
  path: 'collections/:collectionId/study-setup',
  canActivate: [onboardingGuard],
  loadComponent: () =>
    import('./features/study/study-setup-page').then((m) => m.StudySetupPage),
},
{
  path: 'study/:sessionId',
  canActivate: [onboardingGuard],
  loadComponent: () =>
    import('./features/study/study-page').then((m) => m.StudyPage),
},
```

Если `collection.isSystem` и `systemKey === 'irregular_verbs'` — этот экран показывает только
количество и зовёт `createIrregularVerbSession`. Ручного выбора нет.

Обычная тема: пресеты 5/10/15, поле custom (1–50), две кнопки режима. При `MANUAL` — список
карточек темы, только `READY`/`PARTIAL` с переводом (остальные disabled с подписью «ещё готовится»).
Кнопка старта активна, когда отмечено ровно `size` штук.

Перед стартом вызовите `getActiveSession()`. Если сессия есть — не POST, а диалог «Продолжить
занятие» → `router.navigate(['/study', active.id])`. Иначе POST и переход.

Reactive forms, не Signal Forms: так зафиксировано на неделе 1.

Заглушку `StudyPage` создайте уже здесь (spinner + «загрузка»), этапы — следующие шаги.

### Проверка

В браузере / Mini App: тема с ≥5 готовыми словами → setup → random 5 → URL `/study/...`.
Повторный заход в setup той же темы предлагает продолжить, не создаёт вторую сессию.
Custom 51 — ошибка валидации на клиенте. Ручной режим: старт заблокирован при 4 из 5.

### Коммит

`feat(frontend): add study session setup screen`

---

## Шаг 52. Этап знакомства

### Цель

По каждому слову: единица, IPA, аудио, перевод под блюром (тап раскрывает), definition, example.
После последнего слова — следующий этап.

### Файлы

```text
frontend/src/app/features/study/study-page.ts
frontend/src/app/features/study/study-page.html
frontend/src/app/features/study/study-page.scss
frontend/src/app/features/study/stages/study-introduction.ts
frontend/src/app/features/study/stages/study-introduction.html
frontend/src/app/features/study/stages/study-introduction.scss
```

### Действия

`StudyPage` провайдит store, в `ngOnInit` читает `sessionId` из маршрута и зовёт `load`.
Шаблон — переключатель этапов, без бизнес-логики:

```html
@if (store.loading()) {
  <app-spinner />
} @else if (store.error(); as error) {
  <p class="study-page__error">{{ error.message }}</p>
} @else if (store.session()?.status === 'COMPLETED') {
  <app-study-complete />
} @else {
  @switch (store.currentStage()) {
    @case ('INTRODUCTION') { <app-study-introduction /> }
    @case ('MATCHING') { <app-study-matching /> }
    @case ('SENTENCE') { <app-study-sentence /> }
    @case ('DEFINITION') { <app-study-definition /> }
    @case ('VERB_CONJUGATION') { <app-study-verb-conjugation /> }
    @case ('VERB_FORM_PROMPT') { <app-study-verb-form-prompt /> }
  }
}
```

Знакомство берёт `store.currentItem()`. Перевод:

```scss
.introduction__translation {
  filter: blur(8px);
  cursor: pointer;
  user-select: none;

  &--revealed {
    filter: none;
  }
}
```

Тап вызывает `store.revealTranslation()`. Аудио — тот же плеер, что на карточке слова (шаг 42),
не копируйте второй. IPA скрывается, если `null`. Definition/example скрываются, если пустые
(`PARTIAL`). Кнопка «Дальше» всегда доступна — знакомство не экзамен.

После «Дальше» — `advanceAfterCorrectOrReveal()`. На последнем слове store сам сменит этап на
`MATCHING` и сбросит индекс.

Для глаголов introduction показывает три формы и три кнопки аудио. Тот же компонент, другой
шаблон через `@if (session.kind === 'IRREGULAR_VERBS')`, либо отдельный
`study-verb-introduction` — если шаблон перевалит за две независимые вёрстки, разделите.
Не держите word-карточку и три формы в одном наборе классов.

### Проверка

Пройдите 5 слов: блюр снимается тапом, аудио играет, после пятого открывается matching.
Закройте Mini App на третьем слове, откройте — шаг 57 это подтвердит; сейчас достаточно
PATCH после «Дальше» в Network: `currentStage=INTRODUCTION`, `currentItemIndex=1`.

### Коммит

`feat(frontend): add study introduction stage`

---

## Шаг 53. Этап сопоставления: две колонки, тап, вся пачка

### Цель

Слева английские единицы, справа переводы — как пришло в payload. Пользователь нажимает пару.
Drag-and-drop нет. На экране вся пачка целиком.

### Файлы

```text
frontend/src/app/features/study/stages/study-matching.ts
frontend/src/app/features/study/stages/study-matching.html
frontend/src/app/features/study/stages/study-matching.scss
```

### Действия

Рисуйте `matching.left` и `matching.right` как есть. Не вызывайте `sort` / `shuffle` на клиенте —
иначе шаг 46 бессмыслен.

Взаимодействие: тап по левой, тап по правой (порядок любой). Store сверяет `itemId`. Совпало —
оба элемента в состояние « paired », повторно не выбираются. Не совпало — сброс выделения,
короткая вспышка ошибки (класс на 300ms, без `setTimeout` в шаблоне: сигнал `mismatchFlash`
в компоненте).

Вся пачка на одном экране: скролл колонок допустим, пагинации нет. Для 15 слов это ещё умещается
в Mini App.

Кнопка «Дальше» активна при `store.matchingComplete()`. Она зовёт `completeMatchingAndAdvance()`.

Не отправляйте на сервер набор пар: после restore matching начинается с нуля на том же порядке
колонок. Это сознательно. Сохранять 15 пар в PATCH ради редкого закрытия на matching — лишняя
сложность MVP.

### Проверка

Пять слов: неверная пара не засчитывается, верная исчезает из выбора, после всех пар переход
на sentence (или definition, если пачка из фраз). Повторный GET не меняет порядок правой колонки.

Юнит-тест store на matching из шага 50 должен быть зелёным.

### Коммит

`feat(frontend): add tap-to-pair matching stage`

---

## Шаг 54. Подстановка в предложение: ввод, 3 попытки, строгая проверка

### Цель

Показывается список всех слов пачки и предложение с `_____`. Пользователь вводит ответ. Ошибка —
«Попробуй ещё раз». После трёх ошибок — правильный ответ и переход дальше. Phrase этот этап не
проходит.

### Файлы

```text
frontend/src/app/features/study/stages/study-sentence.ts
frontend/src/app/features/study/stages/study-sentence.html
frontend/src/app/features/study/stages/study-sentence.scss
```

### Действия

Список слов — `store.wordList()`, целиком, без вычёркивания. Поле ввода — reactive form control
на компонент, не на store. Submit:

```typescript
protected submit(): void {
  const result = this.store.submitTypedAnswer(this.form.controls.answer.value);
  if (result === 'retry') {
    return;
  }
  void this.store.advanceAfterCorrectOrReveal();
}
```

При `retry` текст «Попробуй ещё раз», поле не очищаем — проще исправить опечатку. При `correct`
и `revealed` — переход. При `revealed` перед переходом покажите ответ секунду: достаточно
состояния `canRevealAnswer()` в шаблоне и кнопки «Дальше», не делайте скрытый auto-advance по
таймеру — в Mini App таймер убивается сворачиванием.

Строгость: `answersMatch` из шага 50. `Clarify` = `clarify`, два пробела = один, `clarfy` ≠
`clarify`.

Phrase: в `stages` нет `SENTENCE`, этот компонент не монтируется. Смешанная пачка: `stageItems`
уже без phrase. Не проверяйте `lexemeType` в шаблоне.

Если у word нет `sentence` (пример не собрался) — не блокируйте сессию: store пропускает item
без задания так же, как phrase. Это должно быть отфильтровано ещё на backend; фронт — предохранитель.

### Проверка

Введите неверный ответ трижды — появляется правильный, «Дальше» ведёт к следующему слову / этапу.
Верный ответ с первого раза сразу двигает вперёд. Пачка из одних фраз этот экран не показывает
(проверьте payload `stages`).

Тест трёх попыток — в `study-session-store.spec.ts` (шаг 50). На неделе 4 (шаг 63) можно добавить
тест компонента; ядро логики уже покрыто.

### Коммит

`feat(frontend): add sentence fill-in stage with three attempts`

---

## Шаг 55. Написание по definition

### Цель

Definition + полный список слов пачки. Пользователь вводит слово. Список не сокращается после
верных ответов. Три попытки, строгая проверка.

### Файлы

```text
frontend/src/app/features/study/stages/study-definition.ts
frontend/src/app/features/study/stages/study-definition.html
frontend/src/app/features/study/stages/study-definition.scss
```

### Действия

Тот же ввод, что на шаге 54. Не копируйте компонент «почти такой же» в shared: экраны разные
(другое поле payload, другой заголовок), общая логика уже в store и `study-answer.ts`.

Список — всегда `wordList` исходного payload, не `filter` по оставшимся. Это продуктовое требование:
подсказка не становится проще к концу пачки.

После последнего слова store вызывает `complete()`. Страница показывает `StudyComplete`: без
баллов, без «7/10», кнопка «К теме». Сложные слова не блокируют завершение.

`PARTIAL` без definition: в payload запасной prompt (перевод). Если и его нет — такого item не
должно быть в сессии (шаг 44).

### Проверка

Пять definition подряд, список из пяти пунктов на каждом. Complete: `GET /study-sessions/active`
→ 404, у карточек `study_count = 1`. Можно сразу стартовать новое занятие.

### Коммит

`feat(frontend): add write-from-definition stage`

---

## Шаг 56. Сокращённый flow фраз и flow неправильных глаголов

### Цель

Фразы идут без sentence. Глаголы: знакомство с тремя формами, затем `go → ? → ?`, затем
`Past Simple of "go"` / `Past Participle of "go"`. Везде 3 попытки и строгая проверка.
`be` принимает `was` и `were`.

### Файлы

```text
frontend/src/app/features/study/stages/study-verb-conjugation.ts
frontend/src/app/features/study/stages/study-verb-conjugation.html
frontend/src/app/features/study/stages/study-verb-conjugation.scss
frontend/src/app/features/study/stages/study-verb-form-prompt.ts
frontend/src/app/features/study/stages/study-verb-form-prompt.html
frontend/src/app/features/study/stages/study-verb-form-prompt.scss
правка study-session-store.ts — курсор formPrompts и два поля conjugation
правка study-session-store.spec.ts
```

### Действия

Фразы: отдельный Angular-flow не нужен. Backend не кладёт `SENTENCE` в `stages`. Не пишите
`if (lexemeType === 'phrase')` в `advanceStage`.

Глаголы, conjugation — два поля на одном экране, подпись `{{ base }} → ? → ?`. Три попытки на
экран: одно неверное поле сжигает попытку; после трёх показать обе формы. Проверка через
`answersMatchAny`. Пустое поле — ошибка.

Глаголы, form prompt — два вопроса на глагол, текст из payload. В MVP кладите плоский
`formPromptQueue` в payload (шаг 49): `current_item_index` указывает в очередь. `be` / Past Simple:
`was` и `were`; `"WAS"` проходит, `"been"` нет. Matching/sentence/definition у глагольной сессии
в `stages` нет.

### Проверка

Тема фраз: introduction → matching → definition → complete, Network без PATCH на `SENTENCE`.

Системная тема: 5 глаголов, conjugation принимает went/gone, form prompt показывает серверную
строку `Past Simple of "go"`. `be` + `were` — успех.

Тесты store: phrase skip; conjugation `be`/`were`; три фейла раскрывают ответ.

### Коммит

`feat(frontend): add phrase skip and irregular verb study flow`

---

## Шаг 57. Восстановление незавершённой сессии

### Цель

Пользователь закрывает Telegram на любом этапе, открывает Mini App снова и продолжает с сохранённых
`current_stage` и `current_item_index`, с тем же payload. Это Definition of Done недели.

### Файлы

```text
frontend/src/app/features/study/study-resume.ts
правка features/collections/collections-page.*   баннер «Продолжить занятие»
правка study-page.ts                             hydrate из GET, не из памяти
backend/tests/test_study_restore.py
frontend/src/app/features/study/study-session-store.spec.ts   доп. кейсы restore
```

### Действия

Цепочка restore:

1. После auth `GET /api/v1/study-sessions/active`.
2. 404 — обычный главный экран.
3. 200 — баннер на списке тем: «У вас есть незавершённое занятие» + кнопка. Не авторедирект:
   пользователь мог открыть приложение, чтобы добавить слово.
4. Переход на `/study/:id` → `store.load(id)` → `hydrate` ставит этап и индекс из ответа.
5. Payload тот же, matching-колонки те же. Попытки = 0, выбранные пары пустые, блюр перевода снова
   включён.

Попытки специально не персистятся: это UI-состояние текущего показа. Закрыл Telegram на второй
ошибке sentence — после открытия снова три попытки на том же предложении. Предложение то же,
потому что оно в payload.

Тесты backend `test_study_restore.py`:

* создать сессию, PATCH `DEFINITION` / index 3, новый GET — те же stage, index, matching.right;
* complete → GET active 404;
* чужой id → 404;
* POST create при активной возвращает ту же сессию, payload не пересобран (сравнить JSON).

Frontend на этом шаге: `hydrate` на `SENTENCE` / index 1 даёт второй word; после hydrate
`attempts() === 0`, пары пустые; phrase-payload без `SENTENCE`.

Критичные frontend-тесты — ядро на неделе 3, UI/E2E на неделе 4:

| Сценарий | Где пишется | Неделя 4 (шаг 63) |
| --- | --- | --- |
| Переходы этапов | `study-session-store.spec.ts` (шаги 50, 56, 57) | можно добавить тест `StudyPage` switch |
| 3 попытки | `study-session-store.spec.ts` + `study-answer.spec.ts` | тест шаблона «Попробуй ещё раз» |
| Phrase skip | store + фикстура payload без SENTENCE | E2E 2 на шаге 64 |
| Matching tap-to-pair | store (шаг 50/53) | компонент колонок |
| Restore | store hydrate + `test_study_restore.py` | E2E 3: close/reopen Telegram |

Ядро — неделя 3. На 63/64 не должны впервые узнать, что matching тасуется на клиенте.

Проверка в Telegram — обязательная, curl недостаточен:

1. Начать занятие, дойти до sentence, слово 2.
2. Закрыть Mini App свайпом (не кнопку «К теме»).
3. `/start` → открыть снова.
4. Баннер → продолжить: тот же пропуск в том же предложении, индекс 2.
5. Дойти до конца, complete.
6. Повторное открытие — баннера нет.

### Проверка

```bash
cd backend
uv run pytest tests/test_study_selection.py tests/test_exercise_payload.py \
  tests/test_study_session_create.py tests/test_study_progress.py tests/test_study_restore.py -v

cd ../frontend
npx tsc --noEmit
npm test -- --watch=false src/app/features/study
```

Затем живой прогон в Telegram по списку выше.

### Коммит

`feat(study): restore unfinished session from saved stage and item`

---

## Definition of Done недели 3

Проверьте каждый пункт вживую:

- [ ] Из темы выбираются количество 5 / 10 / 15 / custom и режим random / manual
- [ ] Random берёт сначала `study_count = 0`, затем изученные; пустые/PENDING/ENRICHING/FAILED не входят
- [ ] `PARTIAL` с переводом учится; без перевода — нет
- [ ] Вторая активная сессия не создаётся: POST возвращает существующую
- [ ] GET отдаёт готовые matching / sentence / definition; повторный GET идентичен
- [ ] Word-flow: знакомство → matching тапами → предложение → definition
- [ ] Phrase-flow без этапа предложения
- [ ] Три ошибки показывают ответ и пускают дальше; список слов на definition не короче
- [ ] Неправильные глаголы: системная тема, три формы, отдельное аудио, `go → ? → ?`, Past Simple of
- [ ] `study_count` и `last_studied_at` обновляются только на complete
- [ ] Закрытие Telegram и повторное открытие продолжает с этапа и индекса
- [ ] Complete снимает активную сессию, можно начать новую
- [ ] Тесты отбора, payload, progress, restore и StudySessionStore зелёные
- [ ] NgRx в проекте нет; HTTP из компонентов этапов нет

### Если неделя затянулась

Режьте в таком порядке:

1. аудио трёх форм глагола (оставьте NULL);
2. custom size — оставьте пресеты 5/10/15;
3. смешанные пачки word+phrase в одном занятии — тестируйте однотипные.

Никогда не режьте: одну активную сессию, серверный payload, persist этапа, skip sentence у phrase,
три попытки, restore в Telegram.

Дальше: [06-week4-stabilization-deploy.md](06-week4-stabilization-deploy.md), шаг 58.
