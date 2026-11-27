from httpx import AsyncClient
from tests.factories import bearer, sign_in_new_device


async def test_patch_updates_level_and_answer_language(client: AsyncClient) -> None:
    token = await sign_in_new_device(client)

    response = await client.patch(
        "/api/v1/users/me",
        json={"cefr_level": "B2", "answer_language": "ru"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["cefr_level"] == "B2"
    assert response.json()["answer_language"] == "ru"
    persisted = (await client.get("/api/v1/users/me", headers=bearer(token))).json()
    assert persisted["cefr_level"] == "B2"


async def test_patch_without_fields_keeps_profile(client: AsyncClient) -> None:
    token = await sign_in_new_device(client)

    response = await client.patch("/api/v1/users/me", json={}, headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["cefr_level"] == "A1"
    assert response.json()["onboarding_completed_at"] is None


async def test_complete_onboarding_sets_timestamp_once(client: AsyncClient) -> None:
    token = await sign_in_new_device(client)

    first = await client.patch(
        "/api/v1/users/me", json={"complete_onboarding": True}, headers=bearer(token)
    )
    second = await client.patch(
        "/api/v1/users/me", json={"complete_onboarding": True}, headers=bearer(token)
    )

    assert first.json()["onboarding_completed_at"] is not None
    assert second.json()["onboarding_completed_at"] == first.json()["onboarding_completed_at"]


async def test_onboarding_cannot_be_reset(client: AsyncClient) -> None:
    token = await sign_in_new_device(client)
    await client.patch(
        "/api/v1/users/me", json={"complete_onboarding": True}, headers=bearer(token)
    )

    response = await client.patch(
        "/api/v1/users/me", json={"complete_onboarding": False}, headers=bearer(token)
    )

    assert response.json()["onboarding_completed_at"] is not None


async def test_patch_rejects_unknown_cefr_level(client: AsyncClient) -> None:
    token = await sign_in_new_device(client)

    response = await client.patch(
        "/api/v1/users/me", json={"cefr_level": "D9"}, headers=bearer(token)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_patch_rejects_unknown_answer_language(client: AsyncClient) -> None:
    token = await sign_in_new_device(client)

    response = await client.patch(
        "/api/v1/users/me", json={"answer_language": "de"}, headers=bearer(token)
    )

    assert response.status_code == 422


async def test_patch_requires_token(client: AsyncClient) -> None:
    response = await client.patch("/api/v1/users/me", json={"cefr_level": "B1"})

    assert response.status_code == 401
