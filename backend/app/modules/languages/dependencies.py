from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.languages.repository import LanguageRepository
from app.modules.languages.service import LanguageService


def get_language_service(session: SessionDep) -> LanguageService:
    return LanguageService(LanguageRepository(session))


type LanguageServiceDep = Annotated[LanguageService, Depends(get_language_service)]
