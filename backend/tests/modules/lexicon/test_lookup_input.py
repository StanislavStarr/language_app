import pytest
from httpx import AsyncClient
from tests.factories import bearer, sign_in_new_device
from tests.modules.lexicon.lookup_helpers import LOOKUP_URL


async def post(client: AsyncClient, body: dict[str, object]) -> int:
    token = await sign_in_new_device(client)
    response = await client.post(LOOKUP_URL, json=body, headers=bearer(token))
    return response.status_code


@pytest.mark.parametrize(
    "body",
    [
        {"source": "manual", "text": ""},
        {"source": "manual", "text": "   "},
        {"source": "manual", "text": "w" * 81},
        {"source": "manual", "text": "one two three four five six"},
        {"source": "manual", "text": "bank", "context_sentence": "c" * 501},
        {"source": "manual"},
        {"text": "bank"},
        {"source": "book", "text": "bank"},
        {"source": "manual", "text": "bank", "unexpected": 1},
    ],
)
async def test_invalid_lookup_input_is_rejected(
    client: AsyncClient, body: dict[str, object]
) -> None:
    assert await post(client, body) == 422


@pytest.mark.parametrize(
    "body",
    [
        {"source": "manual", "text": "w" * 80},
        {"source": "manual", "text": "one two three four five"},
        {"source": "manual", "text": "bank", "context_sentence": "c" * 500},
    ],
)
async def test_lookup_input_at_the_limits_is_accepted(
    client: AsyncClient, body: dict[str, object]
) -> None:
    assert await post(client, body) == 200


async def test_lookup_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(LOOKUP_URL, json={"source": "manual", "text": "bank"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_missing"


async def test_other_endpoints_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/lexemes/1/meanings")).status_code == 401
    assert (await client.post("/api/v1/lexemes/1/ai-meanings", json={})).status_code == 401
