import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from app.core.config import Settings
from app.modules.usage.enums import UsageKind
from app.modules.usage.exceptions import UsageLimitExceededError
from app.modules.usage.repository import DailyUsageRepository
from app.modules.usage.service import UsageService
from app.modules.users.models import User
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from tests.factories import create_user

NOON = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def build_service(
    session: AsyncSession,
    now: datetime = NOON,
    ai_lookup: int = 100,
    book_question: int = 30,
    book_upload: int = 5,
) -> UsageService:
    settings = Settings(
        daily_limit_ai_lookup=ai_lookup,
        daily_limit_book_question=book_question,
        daily_limit_book_upload=book_upload,
    )
    return UsageService(session, DailyUsageRepository(session), settings, lambda: now)


async def test_consume_allows_up_to_the_limit_then_rejects(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    service = build_service(db_session, ai_lookup=3)

    for _ in range(3):
        await service.consume(user.id, UsageKind.AI_LOOKUP)
    with pytest.raises(UsageLimitExceededError) as exceeded:
        await service.consume(user.id, UsageKind.AI_LOOKUP)

    assert exceeded.value.code == "usage_limit_exceeded"
    assert exceeded.value.details == {
        "kind": "ai_lookup",
        "limit": 3,
        "resets_at": "2026-03-11T00:00:00+00:00",
    }


async def test_consume_amount_counts_towards_limit(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    service = build_service(db_session, book_upload=5)

    await service.consume(user.id, UsageKind.BOOK_UPLOAD, amount=3)
    await service.consume(user.id, UsageKind.BOOK_UPLOAD, amount=2)

    with pytest.raises(UsageLimitExceededError):
        await service.consume(user.id, UsageKind.BOOK_UPLOAD)


async def test_consume_rejects_amount_above_limit_on_first_use(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    service = build_service(db_session, book_upload=2)

    with pytest.raises(UsageLimitExceededError):
        await service.consume(user.id, UsageKind.BOOK_UPLOAD, amount=3)
    await service.consume(user.id, UsageKind.BOOK_UPLOAD, amount=2)


async def test_kinds_have_independent_counters(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    service = build_service(db_session, ai_lookup=1, book_question=1)

    await service.consume(user.id, UsageKind.AI_LOOKUP)
    await service.consume(user.id, UsageKind.BOOK_QUESTION)


async def test_users_have_independent_counters(db_session: AsyncSession) -> None:
    first = await create_user(db_session)
    second = await create_user(db_session)
    service = build_service(db_session, ai_lookup=1)

    await service.consume(first.id, UsageKind.AI_LOOKUP)
    await service.consume(second.id, UsageKind.AI_LOOKUP)


async def test_limit_resets_on_next_utc_day(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    today = build_service(db_session, now=datetime(2026, 3, 10, 23, 59, tzinfo=UTC), ai_lookup=1)
    tomorrow = build_service(db_session, now=datetime(2026, 3, 11, 0, 1, tzinfo=UTC), ai_lookup=1)

    await today.consume(user.id, UsageKind.AI_LOOKUP)
    await tomorrow.consume(user.id, UsageKind.AI_LOOKUP)

    with pytest.raises(UsageLimitExceededError):
        await tomorrow.consume(user.id, UsageKind.AI_LOOKUP)


async def test_day_boundary_uses_utc_for_other_timezones(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    plus_three = datetime(2026, 3, 11, 1, 0, tzinfo=UTC).astimezone(timezone(timedelta(hours=3)))
    service = build_service(db_session, now=plus_three, ai_lookup=1)
    same_utc_day = build_service(
        db_session, now=datetime(2026, 3, 11, 20, 0, tzinfo=UTC), ai_lookup=1
    )

    await service.consume(user.id, UsageKind.AI_LOOKUP)

    with pytest.raises(UsageLimitExceededError):
        await same_utc_day.consume(user.id, UsageKind.AI_LOOKUP)


@pytest.fixture
async def committed_session_factory(
    test_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_concurrent_consume_never_exceeds_limit(
    committed_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    limit = 5
    async with committed_session_factory() as setup:
        user = await create_user(setup)
        await setup.commit()

    async def attempt() -> bool:
        async with committed_session_factory() as session:
            service = build_service(session, ai_lookup=limit)
            try:
                await service.consume(user.id, UsageKind.AI_LOOKUP)
            except UsageLimitExceededError:
                return False
            return True

    try:
        results = await asyncio.gather(*(attempt() for _ in range(20)))
    finally:
        async with committed_session_factory() as cleanup:
            await cleanup.execute(delete(User).where(User.id == user.id))
            await cleanup.commit()

    assert results.count(True) == limit


@pytest.mark.parametrize("amount", [0, -1])
async def test_consume_rejects_non_positive_amount(db_session: AsyncSession, amount: int) -> None:
    user = await create_user(db_session)

    with pytest.raises(ValueError, match="positive"):
        await build_service(db_session).consume(user.id, UsageKind.AI_LOOKUP, amount=amount)
