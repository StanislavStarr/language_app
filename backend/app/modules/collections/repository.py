from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collections.models import Collection, CollectionItem


class CollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owned(self, collection_id: UUID, user_id: UUID) -> Collection | None:
        return await self._session.scalar(
            select(Collection).where(Collection.id == collection_id, Collection.user_id == user_id)
        )

    async def list_with_counts(self, user_id: UUID, limit: int) -> list[tuple[Collection, int]]:
        rows = await self._session.execute(
            select(Collection, func.count(CollectionItem.user_vocabulary_item_id))
            .outerjoin(CollectionItem, CollectionItem.collection_id == Collection.id)
            .where(Collection.user_id == user_id)
            .group_by(Collection.id)
            .order_by(Collection.created_at, Collection.id)
            .limit(limit)
        )
        return [(collection, count) for collection, count in rows]

    async def count_for_user(self, user_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count()).select_from(Collection).where(Collection.user_id == user_id)
        )
        return total or 0

    async def name_taken(self, user_id: UUID, name: str, excluding: UUID | None = None) -> bool:
        statement = select(Collection.id).where(
            Collection.user_id == user_id, func.lower(Collection.name) == name.lower()
        )
        if excluding is not None:
            statement = statement.where(Collection.id != excluding)
        return await self._session.scalar(statement.limit(1)) is not None

    async def item_count(self, collection_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(CollectionItem)
            .where(CollectionItem.collection_id == collection_id)
        )
        return total or 0

    async def owned_ids(self, user_id: UUID, collection_ids: Sequence[UUID]) -> set[UUID]:
        rows = await self._session.scalars(
            select(Collection.id).where(
                Collection.user_id == user_id, Collection.id.in_(collection_ids)
            )
        )
        return set(rows)

    async def refs_for_items(self, item_ids: Sequence[UUID]) -> dict[UUID, list[tuple[UUID, str]]]:
        if not item_ids:
            return {}
        rows = await self._session.execute(
            select(CollectionItem.user_vocabulary_item_id, Collection.id, Collection.name)
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(CollectionItem.user_vocabulary_item_id.in_(item_ids))
            .order_by(Collection.name)
        )
        result: dict[UUID, list[tuple[UUID, str]]] = {}
        for item_id, collection_id, name in rows:
            result.setdefault(item_id, []).append((collection_id, name))
        return result

    def add(self, collection: Collection) -> None:
        self._session.add(collection)

    async def delete(self, collection: Collection) -> None:
        await self._session.delete(collection)

    async def add_item(self, collection_ids: Sequence[UUID], item_id: UUID) -> None:
        if not collection_ids:
            return
        statement = (
            insert(CollectionItem)
            .values(
                [
                    {"collection_id": cid, "user_vocabulary_item_id": item_id}
                    for cid in collection_ids
                ]
            )
            .on_conflict_do_nothing()
        )
        await self._session.execute(statement)

    async def remove_item(self, collection_id: UUID, item_id: UUID) -> None:
        await self._session.execute(
            delete(CollectionItem).where(
                CollectionItem.collection_id == collection_id,
                CollectionItem.user_vocabulary_item_id == item_id,
            )
        )
