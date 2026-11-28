from collections.abc import Callable

from app.integrations.ai.provider import SelectSenseRequest, TranslateMeaningsRequest
from app.integrations.ai.schemas.fallback_meanings import FallbackMeaning, FallbackMeaningsOutput
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput
from app.integrations.ai.schemas.translations import TranslatedMeaning, TranslationsOutput
from app.modules.usage.models import DailyUsage
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import bearer, sign_in_new_device

LOOKUP_URL = "/api/v1/lexemes/lookup"


async def lookup(client: AsyncClient, text: str, context: str | None = None) -> Response:
    token = await sign_in_new_device(client)
    body: dict[str, object] = {"source": "manual", "text": text}
    if context is not None:
        body["context_sentence"] = context
    return await client.post(LOOKUP_URL, json=body, headers=bearer(token))


async def ai_units_spent(session: AsyncSession) -> int:
    total = await session.scalar(select(func.coalesce(func.sum(DailyUsage.count), 0)))
    return int(total or 0)


def fallback_output(*glosses: str, found: bool = True) -> FallbackMeaningsOutput:
    return FallbackMeaningsOutput(
        found=found,
        meanings=[FallbackMeaning(part_of_speech="noun", gloss=gloss) for gloss in glosses],
    )


def translations_for(request: TranslateMeaningsRequest) -> TranslationsOutput:
    return TranslationsOutput(
        items=[TranslatedMeaning(meaning_id=m.id, translations=["ссуда"]) for m in request.meanings]
    )


def choose_gloss_containing(
    word: str, confidence: float = 0.9
) -> Callable[[SelectSenseRequest], SenseSelectionOutput]:
    def choose(request: SelectSenseRequest) -> SenseSelectionOutput:
        chosen = next(c.id for c in request.candidates if word in c.gloss)
        return SenseSelectionOutput(
            selected_meaning_id=chosen, contextual_translation="банк", confidence=confidence
        )

    return choose
