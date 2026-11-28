from uuid import UUID

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import bearer, create_lexeme, create_meaning, sign_in_new_device

VOCABULARY_URL = "/api/v1/vocabulary"
COLLECTIONS_URL = "/api/v1/collections"


async def new_headers(client: AsyncClient) -> dict[str, str]:
    return bearer(await sign_in_new_device(client))


async def new_meaning_id(session: AsyncSession, word: str, gloss: str = "A thing.") -> int:
    lexeme = await create_lexeme(session, word)
    meaning = await create_meaning(session, lexeme, gloss, 1, translations={"ru": ["штука"]})
    return meaning.id


async def save(
    client: AsyncClient,
    headers: dict[str, str],
    meaning_id: int,
    collection_ids: list[UUID] | None = None,
    **fields: str,
) -> Response:
    body: dict[str, object] = {"source": "manual", "meaning_id": meaning_id, **fields}
    if collection_ids is not None:
        body["collection_ids"] = [str(collection_id) for collection_id in collection_ids]
    return await client.post(VOCABULARY_URL, json=body, headers=headers)


async def create_collection(
    client: AsyncClient, headers: dict[str, str], name: str = "Travel"
) -> UUID:
    response = await client.post(COLLECTIONS_URL, json={"name": name}, headers=headers)
    assert response.status_code == 201
    return UUID(response.json()["id"])
