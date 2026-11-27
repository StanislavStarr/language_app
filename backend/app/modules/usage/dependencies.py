from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.core.database import SessionDep
from app.modules.usage.repository import DailyUsageRepository
from app.modules.usage.service import UsageService


def get_usage_service(session: SessionDep) -> UsageService:
    return UsageService(session, DailyUsageRepository(session), get_settings())


type UsageServiceDep = Annotated[UsageService, Depends(get_usage_service)]
