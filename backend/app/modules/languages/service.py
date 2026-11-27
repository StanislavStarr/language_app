from collections.abc import Sequence

from app.modules.languages.models import Language
from app.modules.languages.repository import LanguageRepository


class LanguageService:
    def __init__(self, repository: LanguageRepository) -> None:
        self._repository = repository

    async def list_languages(self) -> Sequence[Language]:
        return await self._repository.list_all()
