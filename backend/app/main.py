from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.core import health
from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
from app.core.errors import ErrorResponse, register_error_handlers
from app.core.logging import RequestContextMiddleware, configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_engine(get_settings().database_url)
    app.state.session_factory = create_session_factory(engine)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="English Reader & Vocabulary",
        lifespan=lifespan,
        responses={422: {"model": ErrorResponse}},
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
