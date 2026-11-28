from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI

from app.api import api_router
from app.core import health
from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
from app.core.errors import ErrorResponse, register_error_handlers
from app.core.jobs import jobs_app, run_jobs
from app.core.logging import RequestContextMiddleware, configure_logging
from app.core.rate_limit import SlidingWindowRateLimiter
from app.modules.enrichment.runtime import EnrichmentRuntime, installed_runtime
from app.modules.lexicon.providers import build_lexicon_providers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    app.state.session_factory = create_session_factory(engine)
    try:
        async with httpx.AsyncClient() as http_client:
            providers = build_lexicon_providers(settings, http_client)
            app.state.lexicon_providers = providers
            runtime = EnrichmentRuntime(app.state.session_factory, providers.ai)
            with installed_runtime(runtime):
                async with run_jobs(jobs_app, settings):
                    yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="English Reader & Vocabulary",
        lifespan=lifespan,
        responses={422: {"model": ErrorResponse}},
    )
    app.state.rate_limiter = SlidingWindowRateLimiter(
        settings.rate_limit_per_minute, timedelta(minutes=1)
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
