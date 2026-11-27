from datetime import timedelta
from uuid import uuid4

from app.core.config import get_settings
from app.core.security import issue_access_token
from app.modules.auth.models import AuthIdentity
from app.modules.users.models import User
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import DEVICE_SECRET, bearer, sign_in_new_device


async def count_rows(session: AsyncSession, model: type[User] | type[AuthIdentity]) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_new_device_creates_user_with_ru_en_languages(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await sign_in_new_device(client)

    profile = (await client.get("/api/v1/users/me", headers=bearer(token))).json()
    languages = {
        item["code"]: item["id"] for item in (await client.get("/api/v1/languages")).json()
    }
    assert profile["native_language_id"] == languages["ru"]
    assert profile["learning_language_id"] == languages["en"]
    assert profile["cefr_level"] == "A1"
    assert profile["answer_language"] == "en_simple"
    assert profile["onboarding_completed_at"] is None
    assert await count_rows(db_session, AuthIdentity) == 1


async def test_same_device_with_same_secret_returns_same_user(client: AsyncClient) -> None:
    install_id = uuid4()

    first = await sign_in_new_device(client, install_id)
    second = await sign_in_new_device(client, install_id)

    first_id = (await client.get("/api/v1/users/me", headers=bearer(first))).json()["id"]
    second_id = (await client.get("/api/v1/users/me", headers=bearer(second))).json()["id"]
    assert first_id == second_id


async def test_same_device_with_wrong_secret_is_unauthorized(client: AsyncClient) -> None:
    install_id = uuid4()
    await sign_in_new_device(client, install_id)

    response = await client.post(
        "/api/v1/auth/device",
        json={"install_id": str(install_id), "device_secret": "w" * 43},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_device_credentials"


async def test_different_devices_get_different_users(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await sign_in_new_device(client)
    await sign_in_new_device(client)

    assert await count_rows(db_session, User) == 2


async def test_device_secret_is_stored_hashed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await sign_in_new_device(client)

    stored = await db_session.scalar(select(AuthIdentity.secret_hash))
    assert stored is not None
    assert DEVICE_SECRET not in stored


async def test_device_login_rejects_short_secret(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/device", json={"install_id": str(uuid4()), "device_secret": "short"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_device_login_rejects_non_uuid_install_id(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/device", json={"install_id": "not-a-uuid", "device_secret": DEVICE_SECRET}
    )

    assert response.status_code == 422


async def test_request_without_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_missing"


async def test_request_with_malformed_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me", headers=bearer("garbage"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_invalid"


async def test_request_with_expired_token_is_unauthorized(client: AsyncClient) -> None:
    token = issue_access_token(
        uuid4(), get_settings().jwt_secret.get_secret_value(), timedelta(seconds=-1)
    )

    response = await client.get("/api/v1/users/me", headers=bearer(token))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"


async def test_token_of_unknown_user_is_unauthorized(client: AsyncClient) -> None:
    token = issue_access_token(
        uuid4(), get_settings().jwt_secret.get_secret_value(), timedelta(days=1)
    )

    response = await client.get("/api/v1/users/me", headers=bearer(token))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_invalid"
