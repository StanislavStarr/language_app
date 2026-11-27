from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.usage.enums import UsageKind
from app.modules.usage.exceptions import UsageLimitExceededError
from app.modules.usage.repository import DailyUsageRepository


def utc_now() -> datetime:
    return datetime.now(UTC)


class UsageService:
    def __init__(
        self,
        session: AsyncSession,
        repository: DailyUsageRepository,
        settings: Settings,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._repository = repository
        self._settings = settings
        self._now = now

    async def consume(self, user_id: UUID, kind: UsageKind, amount: int = 1) -> None:
        if amount < 1:
            message = "amount must be positive"
            raise ValueError(message)
        moment = self._now().astimezone(UTC)
        limit = self._daily_limit(kind)
        total = None
        if amount <= limit:
            total = await self._repository.add_within_limit(
                user_id, moment.date(), kind, amount, limit
            )
        if total is None:
            next_midnight = datetime.combine(moment.date() + timedelta(days=1), time(), tzinfo=UTC)
            raise UsageLimitExceededError(kind, limit, next_midnight)
        await self._session.commit()

    def _daily_limit(self, kind: UsageKind) -> int:
        limits = {
            UsageKind.AI_LOOKUP: self._settings.daily_limit_ai_lookup,
            UsageKind.BOOK_QUESTION: self._settings.daily_limit_book_question,
            UsageKind.BOOK_UPLOAD: self._settings.daily_limit_book_upload,
        }
        return limits[kind]
