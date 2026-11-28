from collections.abc import Callable

from app.integrations.ai.provider import AIUnavailableError
from app.modules.lexicon.enums import LexiconSource, TranslationSource
from app.modules.lexicon.models import Meaning, Translation
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import bearer, create_lexeme, create_meaning, sign_in_new_device
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.modules.lexicon.conftest import InstallProviders
from tests.modules.lexicon.lookup_helpers import ai_units_spent, fallback_output, translations_for


def url(lexeme_id: int) -> str:
    return f"/api/v1/lexemes/{lexeme_id}/ai-meanings"


async def bank(session: AsyncSession) -> int:
    lexeme = await create_lexeme(session, "bank")
    await create_meaning(session, lexeme, "An institution for money.", 1)
    return lexeme.id


async def test_extra_meanings_are_added_translated_and_returned(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    lexeme_id = await bank(db_session)
    ai = FakeAIProvider(
        fallback=fallback_output("An institution for money.", "A heap of earth."),
        translations=translations_for,
    )
    install_providers(ai=ai)
    token = await sign_in_new_device(client)

    response = await client.post(
        url(lexeme_id), json={"context_sentence": "A bank of snow."}, headers=bearer(token)
    )

    body = response.json()
    assert response.status_code == 200
    assert [m["gloss"] for m in body["meanings"]] == ["A heap of earth."]
    assert body["meanings"][0]["translations"] == ["ссуда"]
    assert body["has_more"] is False
    stored = list(await db_session.scalars(select(Meaning).order_by(Meaning.sense_order)))
    assert [(m.sense_order, m.source) for m in stored] == [
        (1, LexiconSource.WIKTIONARY),
        (2, LexiconSource.AI),
    ]
    assert (await db_session.scalars(select(Translation.source))).one() == TranslationSource.AI
    assert await ai_units_spent(db_session) == 1


async def test_ai_that_finds_nothing_new_returns_an_empty_page(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    lexeme_id = await bank(db_session)
    install_providers(ai=FakeAIProvider(fallback=fallback_output(found=False)))
    token = await sign_in_new_device(client)

    response = await client.post(url(lexeme_id), json={}, headers=bearer(token))

    assert response.json() == {"meanings": [], "has_more": False}


async def test_unknown_lexeme_is_not_found(
    client: AsyncClient, install_providers: InstallProviders
) -> None:
    install_providers(ai=FakeAIProvider())
    token = await sign_in_new_device(client)

    response = await client.post(url(999_999), json={}, headers=bearer(token))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lexeme_not_found"


async def test_exhausted_limit_is_reported_explicitly(
    client: AsyncClient,
    db_session: AsyncSession,
    install_providers: InstallProviders,
    exhaust_ai_lookups: Callable[[], None],
) -> None:
    lexeme_id = await bank(db_session)
    ai = FakeAIProvider()
    install_providers(ai=ai)
    exhaust_ai_lookups()
    token = await sign_in_new_device(client)

    response = await client.post(url(lexeme_id), json={}, headers=bearer(token))

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "usage_limit_exceeded"
    assert ai.calls == []


async def test_ai_outage_is_reported_as_temporarily_unavailable(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    lexeme_id = await bank(db_session)
    install_providers(ai=FakeAIProvider(error=AIUnavailableError("down")))
    token = await sign_in_new_device(client)

    response = await client.post(url(lexeme_id), json={}, headers=bearer(token))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_temporarily_unavailable"


async def test_missing_ai_configuration_is_reported_without_spending_the_limit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    lexeme_id = await bank(db_session)
    token = await sign_in_new_device(client)

    response = await client.post(url(lexeme_id), json={}, headers=bearer(token))

    assert response.status_code == 503
    assert await ai_units_spent(db_session) == 0


async def test_repeating_the_call_does_not_duplicate_meanings(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    lexeme_id = await bank(db_session)
    install_providers(
        ai=FakeAIProvider(
            fallback=fallback_output("A heap of earth."), translations=translations_for
        )
    )
    token = await sign_in_new_device(client)

    first = await client.post(url(lexeme_id), json={}, headers=bearer(token))
    second = await client.post(url(lexeme_id), json={}, headers=bearer(token))

    assert len(first.json()["meanings"]) == 1
    assert second.json()["meanings"] == []
    assert len(list(await db_session.scalars(select(Meaning)))) == 2
