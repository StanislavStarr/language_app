import asyncio
import importlib
import importlib.util
import pkgutil

import app.modules
from alembic import context
from app.core.config import get_settings
from app.core.database import Base
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config


def load_all_models() -> None:
    for module in pkgutil.iter_modules(app.modules.__path__):
        if importlib.util.find_spec(f"app.modules.{module.name}.models") is not None:
            importlib.import_module(f"app.modules.{module.name}.models")


load_all_models()
target_metadata = Base.metadata


def database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(database_url())
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
