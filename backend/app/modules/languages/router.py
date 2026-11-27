from fastapi import APIRouter

from app.modules.languages.dependencies import LanguageServiceDep
from app.modules.languages.schemas import LanguageResponse

router = APIRouter(prefix="/languages", tags=["languages"])


@router.get("")
async def list_languages(service: LanguageServiceDep) -> list[LanguageResponse]:
    languages = await service.list_languages()
    return [LanguageResponse.model_validate(language) for language in languages]
