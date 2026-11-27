from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.languages.service import LanguageService
from app.modules.users.constants import (
    DEFAULT_ANSWER_LANGUAGE,
    DEFAULT_CEFR_LEVEL,
    LEARNING_LANGUAGE_CODE,
    NATIVE_LANGUAGE_CODE,
)
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserUpdate


class UserService:
    def __init__(
        self,
        session: AsyncSession,
        repository: UserRepository,
        language_service: LanguageService,
    ) -> None:
        self._session = session
        self._repository = repository
        self._language_service = language_service

    async def find_user(self, user_id: UUID) -> User | None:
        return await self._repository.find_by_id(user_id)

    async def add_new_user(self) -> User:
        native_language = await self._language_service.get_language_by_code(NATIVE_LANGUAGE_CODE)
        learning_language = await self._language_service.get_language_by_code(
            LEARNING_LANGUAGE_CODE
        )
        user = User(
            native_language_id=native_language.id,
            learning_language_id=learning_language.id,
            cefr_level=DEFAULT_CEFR_LEVEL,
            answer_language=DEFAULT_ANSWER_LANGUAGE,
        )
        await self._repository.add(user)
        return user

    async def update_profile(self, user: User, payload: UserUpdate) -> User:
        if payload.cefr_level is not None:
            user.cefr_level = payload.cefr_level
        if payload.answer_language is not None:
            user.answer_language = payload.answer_language
        if payload.complete_onboarding and user.onboarding_completed_at is None:
            user.onboarding_completed_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(user)
        return user
