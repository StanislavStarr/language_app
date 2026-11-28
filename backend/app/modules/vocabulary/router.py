from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.errors import ErrorResponse
from app.modules.auth.dependencies import RateLimitedUser, get_rate_limited_user
from app.modules.vocabulary.dependencies import VocabularyServiceDep
from app.modules.vocabulary.schemas import (
    ManualVocabularyCreate,
    VocabularyForms,
    VocabularyItemResponse,
    VocabularyListQuery,
    VocabularyPage,
    VocabularyUpdate,
)

router = APIRouter(
    prefix="/vocabulary",
    tags=["vocabulary"],
    dependencies=[Depends(get_rate_limited_user)],
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)


@router.get("", responses={422: {"model": ErrorResponse}})
async def list_vocabulary(
    user: RateLimitedUser,
    service: VocabularyServiceDep,
    query: Annotated[VocabularyListQuery, Query()],
) -> VocabularyPage:
    return await service.list_items(user, query)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def add_vocabulary_item(
    payload: ManualVocabularyCreate, user: RateLimitedUser, service: VocabularyServiceDep
) -> VocabularyItemResponse:
    return await service.add_item(user, payload)


@router.get("/forms")
async def vocabulary_forms(user: RateLimitedUser, service: VocabularyServiceDep) -> VocabularyForms:
    return await service.forms(user)


@router.get("/{item_id}", responses={404: {"model": ErrorResponse}})
async def get_vocabulary_item(
    item_id: UUID, user: RateLimitedUser, service: VocabularyServiceDep
) -> VocabularyItemResponse:
    return await service.get_item(user, item_id)


@router.patch("/{item_id}", responses={404: {"model": ErrorResponse}})
async def update_vocabulary_item(
    item_id: UUID,
    payload: VocabularyUpdate,
    user: RateLimitedUser,
    service: VocabularyServiceDep,
) -> VocabularyItemResponse:
    return await service.update_item(user, item_id, payload)


@router.delete(
    "/{item_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": ErrorResponse}}
)
async def delete_vocabulary_item(
    item_id: UUID, user: RateLimitedUser, service: VocabularyServiceDep
) -> None:
    await service.delete_item(user, item_id)
