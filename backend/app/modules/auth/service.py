from datetime import timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    decode_access_token,
    hash_device_secret,
    issue_access_token,
    verify_device_secret,
)
from app.modules.auth.enums import AuthProvider
from app.modules.auth.exceptions import (
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    InvalidDeviceCredentialsError,
)
from app.modules.auth.models import AuthIdentity
from app.modules.auth.repository import AuthIdentityRepository
from app.modules.users.models import User
from app.modules.users.service import UserService


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        repository: AuthIdentityRepository,
        user_service: UserService,
        settings: Settings,
    ) -> None:
        self._session = session
        self._repository = repository
        self._user_service = user_service
        self._settings = settings

    async def sign_in_with_device(self, install_id: UUID, device_secret: str) -> str:
        identity = await self._repository.find_device_identity(str(install_id))
        if identity is None:
            identity = await self._register_device(install_id, device_secret)
        if not self._secret_matches(identity, device_secret):
            raise InvalidDeviceCredentialsError
        await self._session.commit()
        return self._issue_token(identity.user_id)

    async def authenticate(self, token: str) -> User:
        try:
            user_id = decode_access_token(token, self._settings.jwt_secret.get_secret_value())
        except TokenExpiredError as error:
            raise ExpiredAccessTokenError from error
        except TokenInvalidError as error:
            raise InvalidAccessTokenError from error
        user = await self._user_service.find_user(user_id)
        if user is None:
            raise InvalidAccessTokenError
        return user

    async def _register_device(self, install_id: UUID, device_secret: str) -> AuthIdentity:
        try:
            async with self._session.begin_nested():
                user = await self._user_service.add_new_user()
                identity = AuthIdentity(
                    user_id=user.id,
                    provider=AuthProvider.DEVICE,
                    external_id=str(install_id),
                    secret_hash=hash_device_secret(device_secret),
                )
                await self._repository.add(identity)
        except IntegrityError:
            existing = await self._repository.find_device_identity(str(install_id))
            if existing is None:
                raise
            return existing
        return identity

    def _secret_matches(self, identity: AuthIdentity, device_secret: str) -> bool:
        return identity.secret_hash is not None and verify_device_secret(
            device_secret, identity.secret_hash
        )

    def _issue_token(self, user_id: UUID) -> str:
        return issue_access_token(
            user_id,
            self._settings.jwt_secret.get_secret_value(),
            timedelta(days=self._settings.access_token_ttl_days),
        )
