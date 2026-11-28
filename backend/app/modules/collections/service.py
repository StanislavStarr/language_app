from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collections.constants import MAX_COLLECTIONS_PER_USER
from app.modules.collections.exceptions import (
    CollectionLimitReachedError,
    CollectionNameTakenError,
    CollectionNotFoundError,
)
from app.modules.collections.models import Collection
from app.modules.collections.repository import CollectionRepository
from app.modules.collections.schemas import (
    CollectionCreate,
    CollectionRef,
    CollectionResponse,
    CollectionUpdate,
)


class OwnedVocabularyItems(Protocol):
    async def require_owned_item(self, user_id: UUID, item_id: UUID) -> None: ...


def to_response(collection: Collection, item_count: int) -> CollectionResponse:
    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        item_count=item_count,
    )


class CollectionService:
    def __init__(
        self,
        session: AsyncSession,
        repository: CollectionRepository,
        items: OwnedVocabularyItems,
    ) -> None:
        self._session = session
        self._repository = repository
        self._items = items

    async def list_collections(self, user_id: UUID) -> list[CollectionResponse]:
        rows = await self._repository.list_with_counts(user_id, MAX_COLLECTIONS_PER_USER)
        return [to_response(collection, count) for collection, count in rows]

    async def create_collection(
        self, user_id: UUID, payload: CollectionCreate
    ) -> CollectionResponse:
        if await self._repository.count_for_user(user_id) >= MAX_COLLECTIONS_PER_USER:
            raise CollectionLimitReachedError(MAX_COLLECTIONS_PER_USER)
        if await self._repository.name_taken(user_id, payload.name):
            raise CollectionNameTakenError(payload.name)
        collection = Collection(user_id=user_id, name=payload.name, description=payload.description)
        self._repository.add(collection)
        await self._commit_unique(collection.name)
        return to_response(collection, 0)

    async def get_collection(self, user_id: UUID, collection_id: UUID) -> CollectionResponse:
        collection = await self._require(user_id, collection_id)
        return to_response(collection, await self._repository.item_count(collection.id))

    async def update_collection(
        self, user_id: UUID, collection_id: UUID, payload: CollectionUpdate
    ) -> CollectionResponse:
        collection = await self._require(user_id, collection_id)
        if payload.name is not None and payload.name != collection.name:
            if await self._repository.name_taken(user_id, payload.name, collection.id):
                raise CollectionNameTakenError(payload.name)
            collection.name = payload.name
        if "description" in payload.model_fields_set:
            collection.description = payload.description
        await self._commit_unique(collection.name)
        return to_response(collection, await self._repository.item_count(collection.id))

    async def delete_collection(self, user_id: UUID, collection_id: UUID) -> None:
        collection = await self._require(user_id, collection_id)
        await self._repository.delete(collection)
        await self._session.commit()

    async def add_item(self, user_id: UUID, collection_id: UUID, item_id: UUID) -> None:
        collection = await self._require(user_id, collection_id)
        await self._items.require_owned_item(user_id, item_id)
        await self._repository.add_item([collection.id], item_id)
        await self._session.commit()

    async def remove_item(self, user_id: UUID, collection_id: UUID, item_id: UUID) -> None:
        collection = await self._require(user_id, collection_id)
        await self._repository.remove_item(collection.id, item_id)
        await self._session.commit()

    async def require_owned(self, user_id: UUID, collection_ids: Sequence[UUID]) -> list[UUID]:
        unique_ids = list(dict.fromkeys(collection_ids))
        owned = await self._repository.owned_ids(user_id, unique_ids)
        for collection_id in unique_ids:
            if collection_id not in owned:
                raise CollectionNotFoundError(collection_id)
        return unique_ids

    async def join_collections(self, item_id: UUID, collection_ids: Sequence[UUID]) -> None:
        await self._repository.add_item(collection_ids, item_id)

    async def refs_for_items(self, item_ids: Sequence[UUID]) -> dict[UUID, list[CollectionRef]]:
        grouped = await self._repository.refs_for_items(item_ids)
        return {
            item_id: [CollectionRef(id=cid, name=name) for cid, name in refs]
            for item_id, refs in grouped.items()
        }

    async def _require(self, user_id: UUID, collection_id: UUID) -> Collection:
        collection = await self._repository.get_owned(collection_id, user_id)
        if collection is None:
            raise CollectionNotFoundError(collection_id)
        return collection

    async def _commit_unique(self, name: str) -> None:
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise CollectionNameTakenError(name) from error
