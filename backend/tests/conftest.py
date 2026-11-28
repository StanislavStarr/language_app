from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.core.database import get_session
from app.core.jobs import jobs_app
from app.main import create_app
from app.modules.vocabulary.dependencies import get_enrichment_scheduler
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from procrastinate import App
from procrastinate.testing import InMemoryConnector
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.fakes.scheduler import RecordingScheduler

TEST_DATABASE_NAME = "vocabulary_test"


def build_alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = make_url(get_settings().database_url).set(database=TEST_DATABASE_NAME)
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database(test_database_url: str) -> Iterator[None]:
    command.upgrade(build_alembic_config(test_database_url), "head")
    yield


@pytest.fixture
async def db_session(test_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        yield session
        await session.close()
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def scheduler() -> RecordingScheduler:
    return RecordingScheduler()


@pytest.fixture
def app(db_session: AsyncSession, scheduler: RecordingScheduler) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_enrichment_scheduler] = lambda: scheduler

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_session] = override_session
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def in_memory_jobs() -> Iterator[App]:
    connector = InMemoryConnector()
    with jobs_app.replace_connector(connector) as app_with_connector:
        yield app_with_connector
