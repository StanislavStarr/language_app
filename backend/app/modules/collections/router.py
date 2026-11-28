from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.errors import ErrorResponse
from app.modules.auth.dependencies import RateLimitedUser, get_rate_limited_user
from app.modules.collections.dependencies import CollectionServiceDep
from app.modules.collections.schemas import (
    CollectionCreate,
    CollectionItemAdd,
    CollectionResponse,
    CollectionUpdate,
)

router = APIRouter(
    prefix="/collections",
    tags=["collections"],
    dependencies=[Depends(get_rate_limited_user)],
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)


@router.get("")
async def list_collections(
    user: RateLimitedUser, service: CollectionServiceDep
) -> list[CollectionResponse]:
    return await service.list_collections(user.id)


@router.post("", status_code=status.HTTP_201_CREATED, responses={409: {"model": ErrorResponse}})
async def create_collection(
    payload: CollectionCreate, user: RateLimitedUser, service: CollectionServiceDep
) -> CollectionResponse:
    return await service.create_collection(user.id, payload)


@router.get("/{collection_id}", responses={404: {"model": ErrorResponse}})
async def get_collection(
    collection_id: UUID, user: RateLimitedUser, service: CollectionServiceDep
) -> CollectionResponse:
    return await service.get_collection(user.id, collection_id)


@router.patch(
    "/{collection_id}", responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}
)
async def update_collection(
    collection_id: UUID,
    payload: CollectionUpdate,
    user: RateLimitedUser,
    service: CollectionServiceDep,
) -> CollectionResponse:
    return await service.update_collection(user.id, collection_id, payload)


@router.delete(
    "/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def delete_collection(
    collection_id: UUID, user: RateLimitedUser, service: CollectionServiceDep
) -> None:
    await service.delete_collection(user.id, collection_id)


@router.post(
    "/{collection_id}/items",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def add_collection_item(
    collection_id: UUID,
    payload: CollectionItemAdd,
    user: RateLimitedUser,
    service: CollectionServiceDep,
) -> None:
    await service.add_item(user.id, collection_id, payload.vocabulary_item_id)


@router.delete(
    "/{collection_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def remove_collection_item(
    collection_id: UUID, item_id: UUID, user: RateLimitedUser, service: CollectionServiceDep
) -> None:
    await service.remove_item(user.id, collection_id, item_id)
