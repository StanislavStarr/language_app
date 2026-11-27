from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

REQUEST_ID_HEADER = "X-Request-ID"

logger = structlog.get_logger()


class AppError(Exception):
    code = "app_error"
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def _error_response(
    request: Request,
    status_code: int,
    error: ErrorBody,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    headers = dict(extra_headers or {})
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers[REQUEST_ID_HEADER] = request_id
    body = ErrorResponse(error=error)
    return JSONResponse(body.model_dump(), status_code=status_code, headers=headers or None)


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    error = ErrorBody(code=exc.code, message=exc.message, details=exc.details)
    return _error_response(request, exc.status_code, error, exc.headers)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [
        {"loc": [str(part) for part in error["loc"]], "type": error["type"], "msg": error["msg"]}
        for error in exc.errors()
    ]
    error = ErrorBody(
        code="validation_error", message="Request validation failed", details={"fields": fields}
    )
    return _error_response(request, status.HTTP_422_UNPROCESSABLE_CONTENT, error)


async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    }
    code = codes.get(exc.status_code, "http_error")
    error = ErrorBody(code=code, message=str(exc.detail))
    return _error_response(request, exc.status_code, error)


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        error_type=type(exc).__name__,
        exc_info=exc,
    )
    error = ErrorBody(code="internal_error", message="Internal server error")
    return _error_response(request, status.HTTP_500_INTERNAL_SERVER_ERROR, error)


def register_error_handlers(app: FastAPI) -> None:
    app.exception_handler(AppError)(_handle_app_error)
    app.exception_handler(RequestValidationError)(_handle_validation_error)
    app.exception_handler(StarletteHTTPException)(_handle_http_error)
    app.exception_handler(Exception)(_handle_unexpected_error)
