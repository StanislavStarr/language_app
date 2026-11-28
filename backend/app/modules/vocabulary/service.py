from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collections.schemas import CollectionRef
from app.modules.collections.service import CollectionService
from app.modules.lexicon.catalog import MeaningCatalog
from app.modules.lexicon.meaning_repository import MeaningDetails
from app.modules.lexicon.schemas import MeaningResponse
from app.modules.users.models import User
from app.modules.vocabulary.constants import MAX_FORMS
from app.modules.vocabulary.cursor import VocabularyCursor
from app.modules.vocabulary.enums import SourceType
from app.modules.vocabulary.exceptions import AlreadyInVocabularyError, VocabularyItemNotFoundError
from app.modules.vocabulary.models import UserVocabularyItem
from app.modules.vocabulary.repository import (
    NewVocabularyItem,
    VocabularyFilter,
    VocabularyRepository,
)
from app.modules.vocabulary.schemas import (
    ManualVocabularyCreate,
    VocabularyContent,
    VocabularyForms,
    VocabularyItemResponse,
    VocabularyLexeme,
    VocabularyListQuery,
    VocabularyPage,
    VocabularyUpdate,
)


class EnrichmentScheduling(Protocol):
    async def schedule(self, item_id: UUID) -> None: ...


class VocabularyService:
    def __init__(
        self,
        session: AsyncSession,
        repository: VocabularyRepository,
        collections: CollectionService,
        catalog: MeaningCatalog,
        scheduler: EnrichmentScheduling,
    ) -> None:
        self._session = session
        self._repository = repository
        self._collections = collections
        self._catalog = catalog
        self._scheduler = scheduler

    async def add_item(self, user: User, payload: ManualVocabularyCreate) -> VocabularyItemResponse:
        await self._catalog.require_meaning(payload.meaning_id)
        collection_ids = await self._collections.require_owned(user.id, payload.collection_ids)
        item, created = await self._repository.create(
            NewVocabularyItem(
                user.id,
                payload.meaning_id,
                SourceType.MANUAL,
                payload.context_sentence,
                payload.context_translation,
            )
        )
        if not created:
            raise AlreadyInVocabularyError(item.id)
        await self._collections.join_collections(item.id, collection_ids)
        await self._session.commit()
        await self._scheduler.schedule(item.id)
        return (await self._responses(user, [item]))[0]

    async def get_item(self, user: User, item_id: UUID) -> VocabularyItemResponse:
        item = await self._require(user, item_id)
        return (await self._responses(user, [item]))[0]

    async def list_items(self, user: User, query: VocabularyListQuery) -> VocabularyPage:
        if query.collection_id is not None:
            await self._collections.require_owned(user.id, [query.collection_id])
        after = VocabularyCursor.decode(query.cursor) if query.cursor else None
        filters = VocabularyFilter(query.collection_id, query.book_id)
        items = await self._repository.page(user.id, filters, after, query.limit + 1)
        shown = items[: query.limit]
        next_cursor = (
            VocabularyCursor(shown[-1].created_at, shown[-1].id).encode()
            if len(items) > query.limit
            else None
        )
        return VocabularyPage(items=await self._responses(user, shown), next_cursor=next_cursor)

    async def update_item(
        self, user: User, item_id: UUID, payload: VocabularyUpdate
    ) -> VocabularyItemResponse:
        item = await self._require(user, item_id)
        if "personal_note" in payload.model_fields_set:
            item.personal_note = payload.personal_note
        if "context_translation" in payload.model_fields_set:
            item.context_translation = payload.context_translation
        await self._session.commit()
        return (await self._responses(user, [item]))[0]

    async def delete_item(self, user: User, item_id: UUID) -> None:
        item = await self._require(user, item_id)
        await self._repository.delete(item)
        await self._session.commit()

    async def forms(self, user: User) -> VocabularyForms:
        meaning_ids = await self._repository.meaning_ids(user.id, MAX_FORMS)
        return VocabularyForms(forms=await self._catalog.forms(meaning_ids, MAX_FORMS))

    async def _require(self, user: User, item_id: UUID) -> UserVocabularyItem:
        item = await self._repository.get_owned(item_id, user.id)
        if item is None:
            raise VocabularyItemNotFoundError(item_id)
        return item

    async def _responses(
        self, user: User, items: Sequence[UserVocabularyItem]
    ) -> list[VocabularyItemResponse]:
        details = await self._catalog.details(
            [item.meaning_id for item in items],
            user.native_language_id,
            [item.meaning_content_id for item in items if item.meaning_content_id is not None],
        )
        refs = await self._collections.refs_for_items([item.id for item in items])
        return [
            to_response(item, details[item.meaning_id], refs.get(item.id, [])) for item in items
        ]


def to_response(
    item: UserVocabularyItem, details: MeaningDetails, collections: list[CollectionRef]
) -> VocabularyItemResponse:
    content = details.content
    return VocabularyItemResponse(
        id=item.id,
        lexeme=VocabularyLexeme(
            id=details.lexeme.id,
            text=details.lexeme.text,
            ipa=details.lexeme.ipa,
            audio_url=details.lexeme.audio_url,
        ),
        meaning=MeaningResponse(
            id=details.meaning.id,
            part_of_speech=details.meaning.part_of_speech,
            gloss=details.meaning.gloss,
            translations=details.translations,
        ),
        content=VocabularyContent(definition=content.definition, example=content.example)
        if content
        else None,
        source_type=item.source_type,
        source_context=item.source_context,
        context_translation=item.context_translation,
        personal_note=item.personal_note,
        enrichment_status=item.enrichment_status,
        study_count=item.study_count,
        collections=collections,
        created_at=item.created_at,
    )
