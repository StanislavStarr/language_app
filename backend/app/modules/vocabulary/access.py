from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vocabulary.exceptions import VocabularyItemNotFoundError
from app.modules.vocabulary.repository import VocabularyRepository


class VocabularyAccess:
    def __init__(self, repository: VocabularyRepository) -> None:
        self._repository = repository

    async def require_owned_item(self, user_id: UUID, item_id: UUID) -> None:
        if await self._repository.get_owned(item_id, user_id) is None:
            raise VocabularyItemNotFoundError(item_id)

    async def saved_meaning_ids(self, user_id: UUID, meaning_ids: Sequence[int]) -> set[int]:
        if not meaning_ids:
            return set()
        return await self._repository.saved_meaning_ids(user_id, meaning_ids)


def build_vocabulary_access(session: AsyncSession) -> VocabularyAccess:
    return VocabularyAccess(VocabularyRepository(session))
