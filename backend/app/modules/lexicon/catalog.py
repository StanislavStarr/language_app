from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.lexicon.exceptions import MeaningNotFoundError
from app.modules.lexicon.meaning_repository import MeaningDetails, MeaningRepository


class MeaningCatalog:
    def __init__(self, repository: MeaningRepository) -> None:
        self._repository = repository

    async def require_meaning(self, meaning_id: int) -> None:
        if not await self._repository.exists(meaning_id):
            raise MeaningNotFoundError(meaning_id)

    async def details(
        self, meaning_ids: Sequence[int], language_id: int, content_ids: Sequence[int]
    ) -> dict[int, MeaningDetails]:
        return await self._repository.details(meaning_ids, language_id, content_ids)

    async def forms(self, meaning_ids: Sequence[int], limit: int) -> list[str]:
        return await self._repository.forms(meaning_ids, limit)


def build_meaning_catalog(session: AsyncSession) -> MeaningCatalog:
    return MeaningCatalog(MeaningRepository(session))
