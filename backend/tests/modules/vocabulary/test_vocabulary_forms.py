from app.modules.lexicon.models import IrregularVerb
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import create_lexeme, create_meaning
from tests.modules.vocabulary.vocabulary_api import (
    VOCABULARY_URL,
    new_headers,
    new_meaning_id,
    save,
)


async def forms_of(client: AsyncClient, headers: dict[str, str]) -> list[str]:
    response = await client.get(f"{VOCABULARY_URL}/forms", headers=headers)
    assert response.status_code == 200
    forms: list[str] = response.json()["forms"]
    return forms


async def test_forms_cover_the_word_its_inflections_and_irregular_forms(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    go = await create_lexeme(db_session, "go", forms=["goes", "going", "went"])
    meaning = await create_meaning(db_session, go, "To move.", 1)
    db_session.add(
        IrregularVerb(
            base_lexeme_id=go.id,
            past_simple="went",
            past_participle="gone / been",
            translation="идти",
        )
    )
    await db_session.flush()
    await save(client, headers, meaning.id)

    assert await forms_of(client, headers) == ["been", "go", "goes", "going", "gone", "went"]


async def test_forms_are_unique_across_several_meanings_of_one_word(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    bank = await create_lexeme(db_session, "bank", forms=["banks"])
    for order, gloss in enumerate(("Money place.", "River edge."), start=1):
        meaning = await create_meaning(db_session, bank, gloss, order)
        await save(client, headers, meaning.id)

    assert await forms_of(client, headers) == ["bank", "banks"]


async def test_forms_of_other_users_words_are_not_included(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    mine = await new_headers(client)
    theirs = await new_headers(client)
    await save(client, theirs, await new_meaning_id(db_session, "secret"))

    assert await forms_of(client, mine) == []


async def test_forms_of_a_removed_word_disappear(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    item = (await save(client, headers, await new_meaning_id(db_session, "bank"))).json()

    await client.delete(f"{VOCABULARY_URL}/{item['id']}", headers=headers)

    assert await forms_of(client, headers) == []
