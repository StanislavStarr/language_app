from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def add(self, user: User) -> None:
        self._session.add(user)
        await self._session.flush()
