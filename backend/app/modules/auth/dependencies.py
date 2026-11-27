from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.database import SessionDep
from app.modules.auth.exceptions import TokenMissingError
from app.modules.auth.repository import AuthIdentityRepository
from app.modules.auth.service import AuthService
from app.modules.users.dependencies import UserServiceDep
from app.modules.users.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(session: SessionDep, user_service: UserServiceDep) -> AuthService:
    return AuthService(session, AuthIdentityRepository(session), user_service, get_settings())


type AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: AuthServiceDep,
) -> User:
    if credentials is None:
        raise TokenMissingError
    return await service.authenticate(credentials.credentials)


type CurrentUser = Annotated[User, Depends(get_current_user)]
