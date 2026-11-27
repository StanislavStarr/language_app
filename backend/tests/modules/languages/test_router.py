from httpx import AsyncClient


async def test_languages_lists_english_and_russian(client: AsyncClient) -> None:
    response = await client.get("/api/v1/languages")

    assert response.status_code == 200
    assert [(item["code"], item["name"]) for item in response.json()] == [
        ("en", "English"),
        ("ru", "Russian"),
    ]
