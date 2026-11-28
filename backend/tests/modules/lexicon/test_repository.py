from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from app.modules.languages.repository import LanguageRepository
from app.modules.lexicon.enums import LexemeType
from app.modules.lexicon.repository import LexemeRepository
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import create_lexeme, create_meaning

TYPO_THRESHOLD = 0.45


async def language_id(session: AsyncSession, code: str) -> int:
    language = await LanguageRepository(session).find_by_code(code)
    assert language is not None
    return language.id


@contextmanager
def count_statements(session: AsyncSession) -> Iterator[list[str]]:
    statements: list[str] = []
    connection = session.sync_session.get_bind()

    def record(_connection: object, _cursor: object, statement: str, *_rest: object) -> None:
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(connection, "before_cursor_execute", record)


async def test_find_by_candidates_returns_exact_text_match(db_session: AsyncSession) -> None:
    bank = await create_lexeme(db_session, "bank")
    english = await language_id(db_session, "en")

    matches = await LexemeRepository(db_session).find_by_candidates(english, ["bank"])

    assert [(match.lexeme.id, match.candidate, match.matched_by_form) for match in matches] == [
        (bank.id, "bank", False)
    ]


async def test_find_by_candidates_resolves_inflected_form_to_its_lemma(
    db_session: AsyncSession,
) -> None:
    go = await create_lexeme(db_session, "go", forms=["went", "gone", "going"])
    english = await language_id(db_session, "en")

    matches = await LexemeRepository(db_session).find_by_candidates(english, ["went"])

    assert [(match.lexeme.id, match.candidate, match.matched_by_form) for match in matches] == [
        (go.id, "went", True)
    ]


async def test_find_by_candidates_orders_by_candidate_priority(db_session: AsyncSession) -> None:
    see = await create_lexeme(db_session, "see", forms=["saw", "seen"])
    saw = await create_lexeme(db_session, "saw")
    english = await language_id(db_session, "en")
    repository = LexemeRepository(db_session)

    exact_first = await repository.find_by_candidates(english, ["saw", "see"])
    lemma_first = await repository.find_by_candidates(english, ["see", "saw"])

    assert [(match.lexeme.id, match.matched_by_form) for match in exact_first] == [
        (saw.id, False),
        (see.id, True),
        (see.id, False),
    ]
    assert [(match.lexeme.id, match.matched_by_form) for match in lemma_first] == [
        (see.id, False),
        (saw.id, False),
        (see.id, True),
    ]


async def test_find_by_candidates_prefers_more_frequent_lexeme_for_the_same_candidate(
    db_session: AsyncSession,
) -> None:
    rare = await create_lexeme(db_session, "leaves", frequency_rank=9000)
    common = await create_lexeme(db_session, "leaf", frequency_rank=500, forms=["leaves"])
    unranked = await create_lexeme(db_session, "foliage", forms=["leaves"])
    english = await language_id(db_session, "en")

    matches = await LexemeRepository(db_session).find_by_candidates(english, ["leaves"])

    assert [match.lexeme.id for match in matches] == [rare.id, common.id, unranked.id]


async def test_find_by_candidates_returns_nothing_for_unknown_words_or_language(
    db_session: AsyncSession,
) -> None:
    await create_lexeme(db_session, "bank")
    english = await language_id(db_session, "en")
    russian = await language_id(db_session, "ru")
    repository = LexemeRepository(db_session)

    assert await repository.find_by_candidates(english, ["zzz"]) == []
    assert await repository.find_by_candidates(english, []) == []
    assert await repository.find_by_candidates(russian, ["bank"]) == []


async def test_list_meanings_orders_by_sense_order_with_translations_of_one_language(
    db_session: AsyncSession,
) -> None:
    bank = await create_lexeme(db_session, "bank")
    second = await create_meaning(
        db_session, bank, "The land alongside a river.", 2, translations={"ru": ["идти"]}
    )
    first = await create_meaning(
        db_session,
        bank,
        "An institution for money.",
        1,
        translations={"ru": ["банк", "ссуда"], "en": ["financial institution"]},
    )
    russian = await language_id(db_session, "ru")

    meanings = await LexemeRepository(db_session).list_meanings(bank.id, russian, 0, 10)

    assert [meaning.id for meaning in meanings] == [first.id, second.id]
    assert [translation.text for translation in meanings[0].translations] == ["банк", "ссуда"]
    assert [translation.text for translation in meanings[1].translations] == ["идти"]


async def test_list_meanings_paginates(db_session: AsyncSession) -> None:
    lexeme = await create_lexeme(db_session, "run")
    created = [
        await create_meaning(db_session, lexeme, f"Meaning {order}.", order)
        for order in range(1, 6)
    ]
    russian = await language_id(db_session, "ru")
    repository = LexemeRepository(db_session)

    page = await repository.list_meanings(lexeme.id, russian, 1, 2)
    beyond = await repository.list_meanings(lexeme.id, russian, 10, 2)

    assert [meaning.id for meaning in page] == [created[1].id, created[2].id]
    assert beyond == []


async def test_list_meanings_loads_translations_without_per_meaning_queries(
    db_session: AsyncSession,
) -> None:
    lexeme = await create_lexeme(db_session, "run")
    for order in range(1, 7):
        await create_meaning(
            db_session,
            lexeme,
            f"Meaning {order}.",
            order,
            translations={"ru": [f"банк {order}"]},
        )
    russian = await language_id(db_session, "ru")
    repository = LexemeRepository(db_session)

    with count_statements(db_session) as statements:
        meanings = await repository.list_meanings(lexeme.id, russian, 0, 10)
        translations = [meaning.translations for meaning in meanings]

    assert len(translations) == 6
    assert len(statements) == 2


async def test_find_similar_suggests_close_spellings_ordered_by_similarity(
    db_session: AsyncSession,
) -> None:
    beautiful = await create_lexeme(db_session, "beautiful")
    await create_lexeme(db_session, "beautify")
    await create_lexeme(db_session, "house")
    english = await language_id(db_session, "en")

    similar = await LexemeRepository(db_session).find_similar(
        english, "beautifull", TYPO_THRESHOLD, 3
    )

    assert next(item.lexeme.id for item in similar) == beautiful.id
    assert all(item.similarity >= TYPO_THRESHOLD for item in similar)
    assert [item.similarity for item in similar] == sorted(
        (item.similarity for item in similar), reverse=True
    )


async def test_find_similar_suggests_phrases(db_session: AsyncSession) -> None:
    phrase = await create_lexeme(db_session, "look forward to", lexeme_type=LexemeType.PHRASE)
    english = await language_id(db_session, "en")

    similar = await LexemeRepository(db_session).find_similar(
        english, "lookk forward to", TYPO_THRESHOLD, 3
    )

    assert [item.lexeme.id for item in similar] == [phrase.id]


@pytest.mark.parametrize(("typo", "expected"), [("hous", True), ("bark", False)])
async def test_find_similar_respects_the_threshold(
    db_session: AsyncSession, typo: str, expected: bool
) -> None:
    await create_lexeme(db_session, "house")
    english = await language_id(db_session, "en")

    similar = await LexemeRepository(db_session).find_similar(english, typo, TYPO_THRESHOLD, 3)

    assert bool(similar) is expected


async def test_find_similar_honours_limit_and_language(db_session: AsyncSession) -> None:
    for text in ("banks", "banked", "banker"):
        await create_lexeme(db_session, text)
    english = await language_id(db_session, "en")
    russian = await language_id(db_session, "ru")
    repository = LexemeRepository(db_session)

    limited = await repository.find_similar(english, "bank", 0.3, 2)
    other_language = await repository.find_similar(russian, "bank", 0.3, 2)

    assert len(limited) == 2
    assert other_language == []
