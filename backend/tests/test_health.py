from collections.abc import AsyncIterator

from app.core.database import get_session
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

UNREACHABLE_DATABASE_URL = "postgresql+psycopg://vocabulary:vocabulary@127.0.0.1:1/vocabulary"


async def test_health_reports_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_reports_ok_when_database_is_alive(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_503_when_database_is_unreachable(
    app: FastAPI, client: AsyncClient
) -> None:
    engine = create_async_engine(UNREACHABLE_DATABASE_URL, poolclass=NullPool)

    async def unreachable_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine) as session:
            yield session

    app.dependency_overrides[get_session] = unreachable_session

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    await engine.dispose()
