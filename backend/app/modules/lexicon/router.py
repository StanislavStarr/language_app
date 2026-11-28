from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.errors import ErrorResponse
from app.modules.auth.dependencies import RateLimitedUser, get_rate_limited_user
from app.modules.lexicon.dependencies import LookupServiceDep
from app.modules.lexicon.schemas import (
    MAX_MEANINGS_PAGE_SIZE,
    MEANINGS_PAGE_SIZE,
    AiMeaningsRequest,
    LookupResponse,
    ManualLookup,
    MeaningsPage,
)

router = APIRouter(
    prefix="/lexemes",
    tags=["lexemes"],
    dependencies=[Depends(get_rate_limited_user)],
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)


@router.post("/lookup")
async def lookup(
    payload: ManualLookup, user: RateLimitedUser, service: LookupServiceDep
) -> LookupResponse:
    return await service.lookup(user.id, payload)


@router.get("/{lexeme_id}/meanings", responses={404: {"model": ErrorResponse}})
async def list_meanings(
    lexeme_id: int,
    service: LookupServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_MEANINGS_PAGE_SIZE)] = MEANINGS_PAGE_SIZE,
) -> MeaningsPage:
    return await service.list_meanings(lexeme_id, offset, limit)


@router.post(
    "/{lexeme_id}/ai-meanings",
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def generate_ai_meanings(
    lexeme_id: int, payload: AiMeaningsRequest, user: RateLimitedUser, service: LookupServiceDep
) -> MeaningsPage:
    return await service.generate_ai_meanings(user.id, lexeme_id, payload)
