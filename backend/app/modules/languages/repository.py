from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.languages.models import Language


class LanguageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> Sequence[Language]:
        result = await self._session.scalars(select(Language).order_by(Language.id))
        return result.all()

    async def find_by_code(self, code: str) -> Language | None:
        return await self._session.scalar(select(Language).where(Language.code == code))
