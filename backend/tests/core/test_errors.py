from app.core.errors import REQUEST_ID_HEADER, AppError
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import BaseModel, Field


class BookNotReadyError(AppError):
    code = "book_not_ready"
    status_code = status.HTTP_409_CONFLICT


class EchoPayload(BaseModel):
    name: str = Field(min_length=3)


def add_probe_routes(app: FastAPI) -> None:
    @app.get("/probe/app-error")
    async def raise_app_error() -> None:
        raise BookNotReadyError("Book is still processing", {"book_id": 7})

    @app.get("/probe/crash")
    async def crash() -> None:
        raise RuntimeError("secret internals")

    @app.post("/probe/echo")
    async def echo(payload: EchoPayload) -> EchoPayload:
        return payload


async def test_app_error_is_rendered_with_its_code_message_and_details(
    app: FastAPI, client: AsyncClient
) -> None:
    add_probe_routes(app)

    response = await client.get("/probe/app-error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "book_not_ready",
            "message": "Book is still processing",
            "details": {"book_id": 7},
        }
    }


async def test_validation_failure_returns_validation_error_with_failing_field(
    app: FastAPI, client: AsyncClient
) -> None:
    add_probe_routes(app)

    response = await client.post("/probe/echo", json={"name": "ab"})

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["fields"][0]["loc"] == ["body", "name"]


async def test_validation_error_does_not_echo_submitted_input(
    app: FastAPI, client: AsyncClient
) -> None:
    add_probe_routes(app)

    response = await client.post("/probe/echo", json={"name": ["private-note"]})

    assert "private" not in response.text
    assert '"input"' not in response.text


async def test_unhandled_exception_returns_internal_error_without_internals(
    app: FastAPI, client: AsyncClient
) -> None:
    add_probe_routes(app)

    response = await client.get("/probe/crash")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text
    assert REQUEST_ID_HEADER in response.headers


async def test_unknown_route_returns_not_found_error(client: AsyncClient) -> None:
    response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
