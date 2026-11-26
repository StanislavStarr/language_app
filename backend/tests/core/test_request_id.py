from app.core.errors import REQUEST_ID_HEADER
from httpx import AsyncClient


async def test_every_response_carries_a_request_id(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert len(response.headers[REQUEST_ID_HEADER]) == 32


async def test_each_request_gets_its_own_request_id(client: AsyncClient) -> None:
    first = await client.get("/health")
    second = await client.get("/health")

    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]
