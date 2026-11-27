from uuid import uuid4

import pytest
from app.core.config import Settings
from app.modules.auth.exceptions import InvalidDeviceCredentialsError
from app.modules.auth.models import AuthIdentity
from app.modules.auth.repository import AuthIdentityRepository
from app.modules.auth.service import AuthService
from app.modules.languages.repository import LanguageRepository
from app.modules.languages.service import LanguageService
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import DEVICE_SECRET


class RepositoryMissingExistingIdentityOnce(AuthIdentityRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._first_lookup = True

    async def find_device_identity(self, install_id: str) -> AuthIdentity | None:
        if self._first_lookup:
            self._first_lookup = False
            return None
        return await super().find_device_identity(install_id)


def build_service(session: AsyncSession, repository: AuthIdentityRepository) -> AuthService:
    users = UserService(
        session, UserRepository(session), LanguageService(LanguageRepository(session))
    )
    return AuthService(session, repository, users, Settings())


async def test_concurrent_first_sign_in_resolves_to_existing_identity(
    db_session: AsyncSession,
) -> None:
    install_id = uuid4()
    await build_service(db_session, AuthIdentityRepository(db_session)).sign_in_with_device(
        install_id, DEVICE_SECRET
    )
    racing = build_service(db_session, RepositoryMissingExistingIdentityOnce(db_session))

    token = await racing.sign_in_with_device(install_id, DEVICE_SECRET)

    assert token
    assert await db_session.scalar(select(func.count()).select_from(AuthIdentity)) == 1


async def test_concurrent_first_sign_in_with_other_secret_is_unauthorized(
    db_session: AsyncSession,
) -> None:
    install_id = uuid4()
    await build_service(db_session, AuthIdentityRepository(db_session)).sign_in_with_device(
        install_id, DEVICE_SECRET
    )
    racing = build_service(db_session, RepositoryMissingExistingIdentityOnce(db_session))

    with pytest.raises(InvalidDeviceCredentialsError):
        await racing.sign_in_with_device(install_id, "o" * 43)
