from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from app.integrations.ai.provider import AIInvalidOutputError, GenerateMeaningContentRequest
from app.integrations.ai.schemas.meaning_content import MeaningContentOutput
from app.modules.enrichment.runtime import EnrichmentRuntime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import create_lexeme, create_meaning
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.modules.lexicon.lookup_helpers import translations_for
from tests.modules.vocabulary.vocabulary_api import VOCABULARY_URL, new_headers, save

CONTENT = MeaningContentOutput(
    definition="A place where people keep their money.",
    example="She opened an account at the bank.",
)


def fake_ai(
    content: Callable[[GenerateMeaningContentRequest], MeaningContentOutput]
    | MeaningContentOutput = CONTENT,
) -> FakeAIProvider:
    return FakeAIProvider(content=content, translations=translations_for)


def invalid_content(_request: GenerateMeaningContentRequest) -> MeaningContentOutput:
    raise AIInvalidOutputError("bad json")


async def meaning_without_translation(session: AsyncSession, word: str = "bank") -> int:
    lexeme = await create_lexeme(session, word, forms=[f"{word}s"])
    return (await create_meaning(session, lexeme, "A place for money.", 1)).id


async def saved_item(
    client: AsyncClient, meaning_id: int, headers: dict[str, str] | None = None
) -> tuple[dict[str, str], UUID]:
    caller = headers or await new_headers(client)
    response = await save(client, caller, meaning_id)
    assert response.status_code == 201
    return caller, UUID(response.json()["id"])


async def card(client: AsyncClient, headers: dict[str, str], item_id: UUID) -> dict[str, object]:
    response = await client.get(f"{VOCABULARY_URL}/{item_id}", headers=headers)
    body: dict[str, object] = response.json()
    return body


def runtime_over(session: AsyncSession, ai: FakeAIProvider | None) -> EnrichmentRuntime:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield session

    return EnrichmentRuntime(factory, ai)
