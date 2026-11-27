from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.languages.dependencies import LanguageServiceDep
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService


def get_user_service(session: SessionDep, language_service: LanguageServiceDep) -> UserService:
    return UserService(session, UserRepository(session), language_service)


type UserServiceDep = Annotated[UserService, Depends(get_user_service)]
