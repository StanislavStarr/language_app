from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, string_enum
from app.modules.vocabulary.constants import (
    MAX_CONTEXT_TRANSLATION_LENGTH,
    MAX_PERSONAL_NOTE_LENGTH,
    MAX_SOURCE_CONTEXT_LENGTH,
)
from app.modules.vocabulary.enums import EnrichmentStatus, SourceType


class UserVocabularyItem(Base):
    __tablename__ = "user_vocabulary_item"
    __table_args__ = (
        UniqueConstraint("user_id", "meaning_id"),
        Index("ix_user_vocabulary_item_user_id_created_at_id", "user_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    meaning_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("meaning.id"))
    source_type: Mapped[SourceType] = mapped_column(string_enum(SourceType, "source_type", 16))
    book_id: Mapped[UUID | None]
    paragraph_id: Mapped[int | None] = mapped_column(BigInteger)
    source_context: Mapped[str | None] = mapped_column(String(MAX_SOURCE_CONTEXT_LENGTH))
    context_translation: Mapped[str | None] = mapped_column(String(MAX_CONTEXT_TRANSLATION_LENGTH))
    personal_note: Mapped[str | None] = mapped_column(String(MAX_PERSONAL_NOTE_LENGTH))
    meaning_content_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("meaning_content.id", ondelete="SET NULL")
    )
    enrichment_status: Mapped[EnrichmentStatus] = mapped_column(
        string_enum(EnrichmentStatus, "enrichment_status", 16),
        default=EnrichmentStatus.PENDING,
    )
    study_count: Mapped[int] = mapped_column(server_default="0", default=0)
    last_studied_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
