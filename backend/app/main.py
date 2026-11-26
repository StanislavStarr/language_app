from fastapi import FastAPI

from app.api import api_router
from app.core import health
from app.core.config import get_settings
from app.core.errors import ErrorResponse, register_error_handlers
from app.core.logging import RequestContextMiddleware, configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="English Reader & Vocabulary",
        responses={422: {"model": ErrorResponse}},
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
