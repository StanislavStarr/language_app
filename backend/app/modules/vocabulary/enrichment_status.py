from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vocabulary.enums import EnrichmentStatus
from app.modules.vocabulary.repository import VocabularyRepository


@dataclass(frozen=True, slots=True)
class EnrichmentTarget:
    item_id: UUID
    user_id: UUID
    meaning_id: int


class VocabularyEnrichment:
    def __init__(self, session: AsyncSession, repository: VocabularyRepository) -> None:
        self._session = session
        self._repository = repository

    async def begin(self, item_id: UUID) -> EnrichmentTarget | None:
        item = await self._repository.get(item_id)
        if item is None or item.enrichment_status == EnrichmentStatus.READY:
            return None
        item.enrichment_status = EnrichmentStatus.ENRICHING
        await self._session.commit()
        return EnrichmentTarget(item.id, item.user_id, item.meaning_id)

    async def finish(
        self, item_id: UUID, status: EnrichmentStatus, meaning_content_id: int | None
    ) -> None:
        item = await self._repository.get(item_id)
        if item is None:
            return
        item.enrichment_status = status
        item.meaning_content_id = meaning_content_id
        await self._session.commit()


def build_vocabulary_enrichment(session: AsyncSession) -> VocabularyEnrichment:
    return VocabularyEnrichment(session, VocabularyRepository(session))
