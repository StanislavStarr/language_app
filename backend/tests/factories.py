from uuid import UUID, uuid4

from app.modules.languages.repository import LanguageRepository
from app.modules.languages.service import LanguageService
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

DEVICE_SECRET = "s" * 43


async def sign_in_new_device(
    client: AsyncClient, install_id: UUID | None = None, device_secret: str = DEVICE_SECRET
) -> str:
    response = await client.post(
        "/api/v1/auth/device",
        json={"install_id": str(install_id or uuid4()), "device_secret": device_secret},
    )
    assert response.status_code == 200
    access_token: str = response.json()["access_token"]
    return access_token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_user(session: AsyncSession) -> User:
    languages = LanguageService(LanguageRepository(session))
    return await UserService(session, UserRepository(session), languages).add_new_user()
