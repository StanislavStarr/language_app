from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, string_enum
from app.modules.languages.enums import CefrLevel
from app.modules.lexicon.enums import (
    LexemeType,
    LexiconSource,
    MeaningContentStatus,
    PartOfSpeech,
    TranslationSource,
)


class Lexeme(Base):
    __tablename__ = "lexeme"
    __table_args__ = (
        UniqueConstraint("language_id", "normalized_text"),
        Index(
            "ix_lexeme_normalized_text_trgm",
            "normalized_text",
            postgresql_using="gin",
            postgresql_ops={"normalized_text": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    language_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("language.id"))
    text: Mapped[str]
    normalized_text: Mapped[str]
    type: Mapped[LexemeType] = mapped_column(string_enum(LexemeType, "lexeme_type", 16))
    ipa: Mapped[str | None]
    audio_url: Mapped[str | None]
    frequency_rank: Mapped[int | None]
    source: Mapped[LexiconSource] = mapped_column(string_enum(LexiconSource, "lexicon_source", 16))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class LexemeForm(Base):
    __tablename__ = "lexeme_form"
    __table_args__ = (UniqueConstraint("lexeme_id", "form_normalized"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lexeme.id", ondelete="CASCADE"))
    form_normalized: Mapped[str] = mapped_column(index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Meaning(Base):
    __tablename__ = "meaning"
    __table_args__ = (
        Index("ix_meaning_lexeme_id_sense_order", "lexeme_id", "sense_order"),
        Index(
            "uq_meaning_lexeme_id_source_external_id",
            "lexeme_id",
            "source_external_id",
            unique=True,
            postgresql_where=text("source_external_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lexeme.id", ondelete="CASCADE"))
    part_of_speech: Mapped[PartOfSpeech] = mapped_column(
        string_enum(PartOfSpeech, "part_of_speech", 16)
    )
    gloss: Mapped[str]
    sense_order: Mapped[int]
    source: Mapped[LexiconSource] = mapped_column(string_enum(LexiconSource, "lexicon_source", 16))
    source_external_id: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    translations: Mapped[list["Translation"]] = relationship(
        lazy="raise", passive_deletes=True, order_by="Translation.id"
    )


class Translation(Base):
    __tablename__ = "translation"
    __table_args__ = (UniqueConstraint("meaning_id", "language_id", "text"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meaning_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meaning.id", ondelete="CASCADE")
    )
    language_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("language.id"))
    text: Mapped[str]
    source: Mapped[TranslationSource] = mapped_column(
        string_enum(TranslationSource, "translation_source", 16)
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MeaningContent(Base):
    __tablename__ = "meaning_content"
    __table_args__ = (UniqueConstraint("meaning_id", "cefr_level", "prompt_version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meaning_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meaning.id", ondelete="CASCADE")
    )
    cefr_level: Mapped[CefrLevel] = mapped_column(string_enum(CefrLevel, "cefr_level", 2))
    definition: Mapped[str | None]
    example: Mapped[str | None]
    status: Mapped[MeaningContentStatus] = mapped_column(
        string_enum(MeaningContentStatus, "meaning_content_status", 16)
    )
    provider: Mapped[str]
    model: Mapped[str]
    prompt_version: Mapped[str]
    generated_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SenseSelection(Base):
    __tablename__ = "sense_selection"
    __table_args__ = (
        UniqueConstraint("lexeme_id", "context_hash", "prompt_version"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lexeme.id", ondelete="CASCADE"))
    context_hash: Mapped[str] = mapped_column(String(64))
    selected_meaning_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("meaning.id", ondelete="SET NULL"), index=True
    )
    contextual_translation: Mapped[str | None]
    confidence: Mapped[float]
    model: Mapped[str]
    prompt_version: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IrregularVerb(Base):
    __tablename__ = "irregular_verb"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    base_lexeme_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lexeme.id", ondelete="CASCADE"), unique=True
    )
    past_simple: Mapped[str]
    past_participle: Mapped[str]
    past_simple_audio_url: Mapped[str | None]
    past_participle_audio_url: Mapped[str | None]
    translation: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
