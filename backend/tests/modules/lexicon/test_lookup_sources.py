from app.integrations.ai.provider import AIProviderError, AIUnavailableError
from app.integrations.dictionary.provider import (
    DictionaryEntry,
    DictionaryMeaning,
    DictionaryUnavailableError,
)
from app.modules.lexicon.enums import LexiconSource, PartOfSpeech
from app.modules.lexicon.models import Lexeme, Meaning
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import create_lexeme, create_meaning
from tests.fakes.dictionary import FakeDictionaryProvider
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.modules.lexicon.conftest import InstallProviders
from tests.modules.lexicon.lookup_helpers import (
    ai_units_spent,
    fallback_output,
    lookup,
    translations_for,
)

BLORP = DictionaryEntry(
    word="blorp",
    ipa="/blorp/",
    audio_url="https://example.org/blorp.mp3",
    meanings=(
        DictionaryMeaning("noun", "A made-up thing.", "Look at that blorp."),
        DictionaryMeaning("adjective", "Silly.", None),
        DictionaryMeaning("noun", "A made-up thing.", None),
    ),
)


async def test_word_missing_from_the_lexicon_is_taken_from_free_dictionary_and_stored(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    dictionary = FakeDictionaryProvider({"blorp": BLORP})
    install_providers(dictionary=dictionary)

    first = (await lookup(client, "blorp")).json()
    second = (await lookup(client, "blorp")).json()

    lexeme = (await db_session.scalars(select(Lexeme))).one()
    meanings = list(await db_session.scalars(select(Meaning).order_by(Meaning.sense_order)))
    assert first["lexeme"]["id"] == second["lexeme"]["id"] == lexeme.id
    assert (lexeme.source, lexeme.ipa) == (LexiconSource.FREE_DICTIONARY, "/blorp/")
    assert lexeme.audio_url == "https://example.org/blorp.mp3"
    assert [(m.part_of_speech, m.gloss) for m in meanings] == [
        (PartOfSpeech.NOUN, "A made-up thing."),
        (PartOfSpeech.ADJECTIVE, "Silly."),
    ]
    assert all(m.source == LexiconSource.FREE_DICTIONARY for m in meanings)
    assert dictionary.lookups == ["blorp"]


async def test_dictionary_failure_does_not_break_the_lookup(
    client: AsyncClient, install_providers: InstallProviders
) -> None:
    install_providers(dictionary=FakeDictionaryProvider(error=DictionaryUnavailableError("down")))

    response = await lookup(client, "blorp")

    assert response.status_code == 200
    assert response.json()["lexeme"] is None


async def test_unknown_word_is_created_from_ai_fallback_and_translated(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    ai = FakeAIProvider(
        fallback=fallback_output("A made-up thing.", "A silly idea."), translations=translations_for
    )
    install_providers(ai=ai)

    body = (await lookup(client, "Blorp")).json()

    lexeme = (await db_session.scalars(select(Lexeme))).one()
    assert lexeme.source == LexiconSource.AI
    assert [(m["gloss"], m["translations"]) for m in body["meanings"]] == [
        ("A made-up thing.", ["ссуда"]),
        ("A silly idea.", ["ссуда"]),
    ]
    assert [name for name, _ in ai.calls] == ["generate_fallback_meanings", "translate_meanings"]
    assert await ai_units_spent(db_session) == 1


async def test_ai_that_does_not_know_the_word_returns_an_empty_answer(
    client: AsyncClient, install_providers: InstallProviders
) -> None:
    install_providers(ai=FakeAIProvider(fallback=fallback_output(found=False)))

    body = (await lookup(client, "qzxwvbnm")).json()

    assert body["lexeme"] is None
    assert body["meanings"] == []
    assert body["typo_suggestion"] is None


async def test_typo_gets_a_suggestion_and_does_not_spend_ai(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    beautiful = await create_lexeme(db_session, "beautiful")
    await create_meaning(db_session, beautiful, "Pleasing to look at.", 1)
    ai = FakeAIProvider()
    install_providers(ai=ai)

    body = (await lookup(client, "beautifull")).json()

    assert body["lexeme"] is None
    assert body["typo_suggestion"] == "beautiful"
    assert ai.calls == []
    assert await ai_units_spent(db_session) == 0


async def test_exact_word_wins_over_a_similar_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    for text in ("bank", "banks"):
        lexeme = await create_lexeme(db_session, text)
        await create_meaning(db_session, lexeme, f"About {text}.", 1, translations={"ru": ["банк"]})

    body = (await lookup(client, "bank")).json()

    assert body["lexeme"]["lemma"] == "bank"
    assert body["typo_suggestion"] is None


async def test_ai_failure_degrades_to_an_empty_answer(
    client: AsyncClient, install_providers: InstallProviders
) -> None:
    install_providers(ai=FakeAIProvider(error=AIUnavailableError("down")))

    response = await lookup(client, "blorp")

    assert response.status_code == 200
    assert response.json()["lexeme"] is None
    assert response.json()["ai_limited"] is False


async def test_ai_provider_error_degrades_too(
    client: AsyncClient, install_providers: InstallProviders
) -> None:
    install_providers(ai=FakeAIProvider(error=AIProviderError("bad key")))

    assert (await lookup(client, "blorp")).json()["lexeme"] is None
