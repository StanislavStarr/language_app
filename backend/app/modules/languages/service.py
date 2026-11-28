from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.languages.exceptions import LanguageNotFoundError
from app.modules.languages.models import Language
from app.modules.languages.repository import LanguageRepository


class LanguageService:
    def __init__(self, repository: LanguageRepository) -> None:
        self._repository = repository

    async def list_languages(self) -> Sequence[Language]:
        return await self._repository.list_all()

    async def get_language_by_code(self, code: str) -> Language:
        language = await self._repository.find_by_code(code)
        if language is None:
            raise LanguageNotFoundError(code)
        return language


def build_language_service(session: AsyncSession) -> LanguageService:
    return LanguageService(LanguageRepository(session))
