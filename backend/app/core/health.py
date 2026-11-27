from typing import Literal

import structlog
from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionDep
from app.core.errors import AppError, ErrorResponse

router = APIRouter(tags=["health"])
logger = structlog.get_logger()


class HealthResponse(BaseModel):
    status: Literal["ok"]


class DatabaseUnavailableError(AppError):
    code = "database_unavailable"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", responses={503: {"model": ErrorResponse}})
async def ready(session: SessionDep) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("database_unavailable", error_type=type(exc).__name__)
        raise DatabaseUnavailableError("Database is unavailable") from exc
    return HealthResponse(status="ok")
