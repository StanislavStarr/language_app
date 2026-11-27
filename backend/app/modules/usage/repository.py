from datetime import date
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.usage.enums import UsageKind
from app.modules.usage.models import DailyUsage


class DailyUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_within_limit(
        self, user_id: UUID, day: date, kind: UsageKind, amount: int, limit: int
    ) -> int | None:
        statement = (
            insert(DailyUsage)
            .values(user_id=user_id, day=day, kind=kind, count=amount)
            .on_conflict_do_update(
                index_elements=[DailyUsage.user_id, DailyUsage.day, DailyUsage.kind],
                set_={"count": DailyUsage.count + amount},
                where=DailyUsage.count + amount <= limit,
            )
            .returning(DailyUsage.count)
        )
        return await self._session.scalar(statement)
