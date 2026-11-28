from collections.abc import Awaitable, Callable

import pytest
from app.modules.languages.enums import CefrLevel
from app.modules.lexicon.enums import MeaningContentStatus
from app.modules.lexicon.models import (
    IrregularVerb,
    Lexeme,
    LexemeForm,
    Meaning,
    MeaningContent,
    SenseSelection,
    Translation,
)
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import create_lexeme, create_meaning

CONTEXT_HASH = "a" * 64


async def count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def violated_constraint(
    session: AsyncSession, statement_factory: Callable[[], Awaitable[object]]
) -> str | None:
    try:
        async with session.begin_nested():
            await statement_factory()
    except IntegrityError as error:
        diagnostics = getattr(error.orig, "diag", None)
        return getattr(diagnostics, "constraint_name", None)
    return None


async def test_lexeme_text_is_unique_per_language(db_session: AsyncSession) -> None:
    await create_lexeme(db_session, "bank")

    assert (
        await violated_constraint(db_session, lambda: create_lexeme(db_session, "bank"))
        == "uq_lexeme_language_id"
    )


async def test_form_is_unique_per_lexeme(db_session: AsyncSession) -> None:
    go = await create_lexeme(db_session, "go", forms=["went"])

    async def duplicate() -> None:
        db_session.add(LexemeForm(lexeme_id=go.id, form_normalized="went"))
        await db_session.flush()

    assert await violated_constraint(db_session, duplicate) == "uq_lexeme_form_lexeme_id"


async def test_same_form_may_belong_to_different_lexemes(db_session: AsyncSession) -> None:
    await create_lexeme(db_session, "see", forms=["saw"])
    await create_lexeme(db_session, "saw", forms=["saw"])

    assert await count(db_session, LexemeForm) == 2


async def test_translation_is_unique_per_meaning_and_language(db_session: AsyncSession) -> None:
    bank = await create_lexeme(db_session, "bank")
    meaning = await create_meaning(db_session, bank, "A bank.", 1, translations={"ru": ["банк"]})
    existing = (await db_session.scalars(select(Translation))).one()

    async def duplicate() -> None:
        db_session.add(
            Translation(
                meaning_id=meaning.id,
                language_id=existing.language_id,
                text="банк",
                source=existing.source,
            )
        )
        await db_session.flush()

    assert await violated_constraint(db_session, duplicate) == "uq_translation_meaning_id"


async def test_deleting_a_lexeme_removes_its_dependent_rows(db_session: AsyncSession) -> None:
    bank = await create_lexeme(db_session, "bank", forms=["banks"])
    meaning = await create_meaning(db_session, bank, "A bank.", 1, translations={"ru": ["банк"]})
    db_session.add(
        SenseSelection(
            lexeme_id=bank.id,
            context_hash=CONTEXT_HASH,
            selected_meaning_id=meaning.id,
            confidence=0.9,
            model="m",
            prompt_version="v1",
        )
    )
    await db_session.flush()

    await db_session.execute(delete(Lexeme).where(Lexeme.id == bank.id))

    for model in (LexemeForm, Meaning, Translation, SenseSelection):
        assert await count(db_session, model) == 0


async def test_deleting_a_meaning_keeps_the_cached_sense_selection(
    db_session: AsyncSession,
) -> None:
    bank = await create_lexeme(db_session, "bank")
    meaning = await create_meaning(db_session, bank, "A bank.", 1)
    db_session.add(
        SenseSelection(
            lexeme_id=bank.id,
            context_hash=CONTEXT_HASH,
            selected_meaning_id=meaning.id,
            confidence=0.5,
            model="m",
            prompt_version="v1",
        )
    )
    await db_session.flush()

    await db_session.execute(delete(Meaning).where(Meaning.id == meaning.id))
    selection = (await db_session.scalars(select(SenseSelection))).one()
    await db_session.refresh(selection)

    assert selection.selected_meaning_id is None


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
async def test_sense_selection_confidence_must_be_between_zero_and_one(
    db_session: AsyncSession, confidence: float
) -> None:
    bank = await create_lexeme(db_session, "bank")

    async def insert() -> None:
        db_session.add(
            SenseSelection(
                lexeme_id=bank.id,
                context_hash=CONTEXT_HASH,
                confidence=confidence,
                model="m",
                prompt_version="v1",
            )
        )
        await db_session.flush()

    assert await violated_constraint(db_session, insert) == "ck_sense_selection_confidence_range"


async def test_sense_selection_is_cached_once_per_context_and_prompt_version(
    db_session: AsyncSession,
) -> None:
    bank = await create_lexeme(db_session, "bank")

    async def insert(prompt_version: str) -> None:
        db_session.add(
            SenseSelection(
                lexeme_id=bank.id,
                context_hash=CONTEXT_HASH,
                confidence=0.7,
                model="m",
                prompt_version=prompt_version,
            )
        )
        await db_session.flush()

    await insert("v1")
    await insert("v2")

    assert (
        await violated_constraint(db_session, lambda: insert("v1"))
        == "uq_sense_selection_lexeme_id"
    )


async def test_meaning_content_is_unique_per_level_and_prompt_version(
    db_session: AsyncSession,
) -> None:
    bank = await create_lexeme(db_session, "bank")
    meaning = await create_meaning(db_session, bank, "A bank.", 1)

    async def insert(level: CefrLevel) -> None:
        db_session.add(
            MeaningContent(
                meaning_id=meaning.id,
                cefr_level=level,
                status=MeaningContentStatus.PENDING,
                provider="openai",
                model="m",
                prompt_version="v1",
            )
        )
        await db_session.flush()

    await insert(CefrLevel.B1)
    await insert(CefrLevel.B2)

    assert (
        await violated_constraint(db_session, lambda: insert(CefrLevel.B1))
        == "uq_meaning_content_meaning_id"
    )


async def test_irregular_verb_is_unique_per_base_lexeme(db_session: AsyncSession) -> None:
    go = await create_lexeme(db_session, "go")

    async def insert() -> None:
        db_session.add(
            IrregularVerb(
                base_lexeme_id=go.id, past_simple="went", past_participle="gone", translation="идти"
            )
        )
        await db_session.flush()

    await insert()

    assert await violated_constraint(db_session, insert) == "uq_irregular_verb_base_lexeme_id"


@pytest.mark.parametrize(
    ("table", "column", "constraint"),
    [
        ("lexeme", "type", "ck_lexeme_lexeme_type"),
        ("lexeme", "source", "ck_lexeme_lexicon_source"),
        ("meaning", "part_of_speech", "ck_meaning_part_of_speech"),
        ("translation", "source", "ck_translation_translation_source"),
        ("meaning_content", "status", "ck_meaning_content_meaning_content_status"),
        ("meaning_content", "cefr_level", "ck_meaning_content_cefr_level"),
    ],
)
async def test_enum_columns_reject_unknown_values(
    db_session: AsyncSession, table: str, column: str, constraint: str
) -> None:
    async def update() -> None:
        await db_session.execute(
            text(f"UPDATE {table} SET {column} = 'x'")  # noqa: S608
        )

    bank = await create_lexeme(db_session, "bank")
    meaning = await create_meaning(db_session, bank, "A bank.", 1, translations={"ru": ["банк"]})
    db_session.add(
        MeaningContent(
            meaning_id=meaning.id,
            cefr_level=CefrLevel.B1,
            status=MeaningContentStatus.PENDING,
            provider="openai",
            model="m",
            prompt_version="v1",
        )
    )
    await db_session.flush()

    assert await violated_constraint(db_session, update) == constraint
