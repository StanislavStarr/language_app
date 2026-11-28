from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Boolean, literal_column, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collections.membership import item_ids_in_collection
from app.modules.vocabulary.cursor import VocabularyCursor
from app.modules.vocabulary.enums import EnrichmentStatus, SourceType
from app.modules.vocabulary.models import UserVocabularyItem


@dataclass(frozen=True, slots=True)
class NewVocabularyItem:
    user_id: UUID
    meaning_id: int
    source_type: SourceType
    source_context: str | None
    context_translation: str | None


@dataclass(frozen=True, slots=True)
class VocabularyFilter:
    collection_id: UUID | None
    book_id: UUID | None


class VocabularyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, new: NewVocabularyItem) -> tuple[UserVocabularyItem, bool]:
        statement = (
            insert(UserVocabularyItem)
            .values(
                user_id=new.user_id,
                meaning_id=new.meaning_id,
                source_type=new.source_type,
                source_context=new.source_context,
                context_translation=new.context_translation,
                enrichment_status=EnrichmentStatus.PENDING,
            )
            .on_conflict_do_update(
                index_elements=[UserVocabularyItem.user_id, UserVocabularyItem.meaning_id],
                set_={"user_id": new.user_id},
            )
            .returning(
                UserVocabularyItem.id, literal_column("(xmax = 0)", Boolean).label("created")
            )
        )
        result = await self._session.execute(statement)
        item_id, created = result.one()
        item = await self._session.get_one(UserVocabularyItem, item_id)
        return item, bool(created)

    async def get_owned(self, item_id: UUID, user_id: UUID) -> UserVocabularyItem | None:
        return await self._session.scalar(
            select(UserVocabularyItem).where(
                UserVocabularyItem.id == item_id, UserVocabularyItem.user_id == user_id
            )
        )

    async def page(
        self,
        user_id: UUID,
        filters: VocabularyFilter,
        after: VocabularyCursor | None,
        limit: int,
    ) -> list[UserVocabularyItem]:
        statement = select(UserVocabularyItem).where(UserVocabularyItem.user_id == user_id)
        if filters.collection_id is not None:
            statement = statement.where(
                UserVocabularyItem.id.in_(item_ids_in_collection(filters.collection_id))
            )
        if filters.book_id is not None:
            statement = statement.where(UserVocabularyItem.book_id == filters.book_id)
        if after is not None:
            statement = statement.where(
                tuple_(UserVocabularyItem.created_at, UserVocabularyItem.id)
                < tuple_(after.created_at, after.item_id)
            )
        statement = statement.order_by(
            UserVocabularyItem.created_at.desc(), UserVocabularyItem.id.desc()
        ).limit(limit)
        return list(await self._session.scalars(statement))

    async def delete(self, item: UserVocabularyItem) -> None:
        await self._session.delete(item)

    async def saved_meaning_ids(self, user_id: UUID, meaning_ids: Sequence[int]) -> set[int]:
        rows = await self._session.scalars(
            select(UserVocabularyItem.meaning_id).where(
                UserVocabularyItem.user_id == user_id,
                UserVocabularyItem.meaning_id.in_(meaning_ids),
            )
        )
        return set(rows)

    async def meaning_ids(self, user_id: UUID, limit: int) -> list[int]:
        rows = await self._session.scalars(
            select(UserVocabularyItem.meaning_id)
            .where(UserVocabularyItem.user_id == user_id)
            .order_by(UserVocabularyItem.created_at, UserVocabularyItem.id)
            .limit(limit)
        )
        return list(rows)
