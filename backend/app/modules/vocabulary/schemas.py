from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.collections.schemas import CollectionRef
from app.modules.lexicon.schemas import MeaningResponse
from app.modules.vocabulary.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_COLLECTIONS_PER_ITEM,
    MAX_CONTEXT_TRANSLATION_LENGTH,
    MAX_PAGE_SIZE,
    MAX_PERSONAL_NOTE_LENGTH,
    MAX_SOURCE_CONTEXT_LENGTH,
)
from app.modules.vocabulary.enums import EnrichmentStatus, SourceType


class ManualVocabularyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["manual"]
    meaning_id: int
    collection_ids: list[UUID] = Field(default_factory=list, max_length=MAX_COLLECTIONS_PER_ITEM)
    context_sentence: str | None = Field(default=None, max_length=MAX_SOURCE_CONTEXT_LENGTH)
    context_translation: str | None = Field(default=None, max_length=MAX_CONTEXT_TRANSLATION_LENGTH)


class VocabularyListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: UUID | None = None
    book_id: UUID | None = None
    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class VocabularyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    personal_note: str | None = Field(default=None, max_length=MAX_PERSONAL_NOTE_LENGTH)
    context_translation: str | None = Field(default=None, max_length=MAX_CONTEXT_TRANSLATION_LENGTH)


class VocabularyLexeme(BaseModel):
    id: int
    text: str
    ipa: str | None
    audio_url: str | None


class VocabularyContent(BaseModel):
    definition: str | None
    example: str | None


class VocabularyItemResponse(BaseModel):
    id: UUID
    lexeme: VocabularyLexeme
    meaning: MeaningResponse
    content: VocabularyContent | None
    source_type: SourceType
    source_context: str | None
    context_translation: str | None
    personal_note: str | None
    enrichment_status: EnrichmentStatus
    study_count: int
    collections: list[CollectionRef]
    created_at: datetime


class VocabularyPage(BaseModel):
    items: list[VocabularyItemResponse]
    next_cursor: str | None


class VocabularyForms(BaseModel):
    forms: list[str]
