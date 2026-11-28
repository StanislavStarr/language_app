from collections.abc import Callable

from app.integrations.ai.provider import (
    AIInvalidOutputError,
    AIUnavailableError,
    SelectSenseRequest,
)
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput
from app.modules.lexicon.enums import TranslationSource
from app.modules.lexicon.models import SenseSelection, Translation
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import create_lexeme, create_meaning
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.modules.lexicon.conftest import InstallProviders
from tests.modules.lexicon.lookup_helpers import (
    ai_units_spent,
    choose_gloss_containing,
    fallback_output,
    lookup,
    translations_for,
)

SENTENCE = "They had a picnic on the bank of the river."


async def bank_with_two_meanings(session: AsyncSession, translated: bool = True) -> int:
    bank = await create_lexeme(session, "bank")
    translations = {"ru": ["банк"]} if translated else {}
    await create_meaning(session, bank, "An institution for money.", 1, translations=translations)
    await create_meaning(session, bank, "The land beside a river.", 2, translations=translations)
    return bank.id


async def test_context_chooses_a_meaning_and_it_is_shown_first(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    await bank_with_two_meanings(db_session)
    install_providers(ai=FakeAIProvider(sense=choose_gloss_containing("river", 0.93)))

    body = (await lookup(client, "bank", SENTENCE)).json()

    assert body["recommended"]["contextual_translation"] == "банк"
    assert body["recommended"]["confidence"] == 0.93
    assert body["meanings"][0]["id"] == body["recommended"]["meaning_id"]
    assert body["meanings"][0]["gloss"] == "The land beside a river."


async def test_second_lookup_with_the_same_context_does_not_call_ai(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    await bank_with_two_meanings(db_session)
    ai = FakeAIProvider(sense=choose_gloss_containing("river"))
    install_providers(ai=ai)

    first = (await lookup(client, "bank", SENTENCE)).json()
    second = (await lookup(client, "Bank", f"  {SENTENCE}  ")).json()

    assert [name for name, _ in ai.calls] == ["select_sense"]
    assert second["recommended"] == first["recommended"]
    assert await ai_units_spent(db_session) == 1
    assert await db_session.scalar(select(func.count()).select_from(SenseSelection)) == 1


async def test_cached_choice_stores_only_a_hash_of_the_context(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    await bank_with_two_meanings(db_session)
    install_providers(ai=FakeAIProvider(sense=choose_gloss_containing("river")))

    await lookup(client, "bank", SENTENCE)

    selection = (await db_session.scalars(select(SenseSelection))).one()
    assert len(selection.context_hash) == 64
    assert "picnic" not in str(selection.__dict__)


async def test_lookup_without_context_does_not_select_a_meaning(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    await bank_with_two_meanings(db_session)
    ai = FakeAIProvider()
    install_providers(ai=ai)

    body = (await lookup(client, "bank")).json()

    assert body["recommended"] is None
    assert ai.calls == []


async def test_a_single_meaning_needs_no_selection(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    lexeme = await create_lexeme(db_session, "river")
    await create_meaning(
        db_session, lexeme, "A stream of water.", 1, translations={"ru": ["касса"]}
    )
    ai = FakeAIProvider()
    install_providers(ai=ai)

    body = (await lookup(client, "river", SENTENCE)).json()

    assert body["recommended"] is None
    assert ai.calls == []


async def test_no_fitting_meaning_is_cached_without_a_recommendation(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    await bank_with_two_meanings(db_session)
    none_fits = SenseSelectionOutput(
        selected_meaning_id=None, contextual_translation=None, confidence=0.2
    )
    ai = FakeAIProvider(sense=none_fits)
    install_providers(ai=ai)

    first = (await lookup(client, "bank", SENTENCE)).json()
    await lookup(client, "bank", SENTENCE)

    assert first["recommended"] is None
    assert len(ai.calls) == 1


async def test_invalid_output_is_retried_once(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    await bank_with_two_meanings(db_session)
    choose = choose_gloss_containing("river")
    attempts = 0

    def flaky(request: SelectSenseRequest) -> SenseSelectionOutput:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AIInvalidOutputError("bad json")
        return choose(request)

    install_providers(ai=FakeAIProvider(sense=flaky))

    body = (await lookup(client, "bank", SENTENCE)).json()

    assert attempts == 2
    assert body["recommended"] is not None


async def test_persistently_invalid_output_degrades_without_a_recommendation(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    await bank_with_two_meanings(db_session)
    ai = FakeAIProvider(error=AIInvalidOutputError("bad json"))
    install_providers(ai=ai)

    response = await lookup(client, "bank", SENTENCE)

    assert response.status_code == 200
    assert response.json()["recommended"] is None
    assert len(ai.calls) == 2
    assert await db_session.scalar(select(func.count()).select_from(SenseSelection)) == 0


async def test_ai_outage_still_returns_the_dictionary_meanings(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    await bank_with_two_meanings(db_session, translated=False)
    install_providers(ai=FakeAIProvider(error=AIUnavailableError("down")))

    body = (await lookup(client, "bank", SENTENCE)).json()

    assert [m["translations"] for m in body["meanings"]] == [[], []]
    assert body["recommended"] is None


async def test_missing_translations_are_filled_in_and_stored_once(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    await bank_with_two_meanings(db_session, translated=False)
    ai = FakeAIProvider(translations=translations_for)
    install_providers(ai=ai)

    first = (await lookup(client, "bank")).json()
    second = (await lookup(client, "bank")).json()

    assert [m["translations"] for m in first["meanings"]] == [["ссуда"], ["ссуда"]]
    assert [m["translations"] for m in second["meanings"]] == [["ссуда"], ["ссуда"]]
    assert len(ai.calls) == 1
    stored = list(await db_session.scalars(select(Translation)))
    assert {t.source for t in stored} == {TranslationSource.AI}
    assert len(stored) == 2


async def test_exhausted_limit_returns_dictionary_data_and_flags_it(
    client: AsyncClient,
    db_session: AsyncSession,
    install_providers: InstallProviders,
    exhaust_ai_lookups: Callable[[], None],
) -> None:
    await bank_with_two_meanings(db_session, translated=False)
    ai = FakeAIProvider()
    install_providers(ai=ai)
    exhaust_ai_lookups()

    body = (await lookup(client, "bank", SENTENCE)).json()

    assert body["ai_limited"] is True
    assert body["recommended"] is None
    assert len(body["meanings"]) == 2
    assert ai.calls == []


async def test_exhausted_limit_blocks_the_ai_fallback_for_unknown_words(
    client: AsyncClient,
    install_providers: InstallProviders,
    exhaust_ai_lookups: Callable[[], None],
) -> None:
    ai = FakeAIProvider(fallback=fallback_output("Some thing."))
    install_providers(ai=ai)
    exhaust_ai_lookups()

    body = (await lookup(client, "blorp")).json()

    assert body["lexeme"] is None
    assert body["ai_limited"] is True
    assert ai.calls == []
