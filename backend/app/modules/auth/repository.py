from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import AuthProvider
from app.modules.auth.models import AuthIdentity


class AuthIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_device_identity(self, install_id: str) -> AuthIdentity | None:
        statement = select(AuthIdentity).where(
            AuthIdentity.provider == AuthProvider.DEVICE,
            AuthIdentity.external_id == install_id,
        )
        return await self._session.scalar(statement)

    async def add(self, identity: AuthIdentity) -> None:
        self._session.add(identity)
        await self._session.flush()
