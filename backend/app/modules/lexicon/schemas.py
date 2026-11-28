from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.integrations.nlp.normalization import normalize_text
from app.modules.lexicon.enums import PartOfSpeech

MAX_LOOKUP_TEXT_LENGTH = 80
MAX_LOOKUP_WORDS = 5
MAX_CONTEXT_LENGTH = 500
MEANINGS_PAGE_SIZE = 3
MAX_MEANINGS_PAGE_SIZE = 20


class ManualLookup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["manual"]
    text: str = Field(min_length=1, max_length=MAX_LOOKUP_TEXT_LENGTH)
    context_sentence: str | None = Field(default=None, max_length=MAX_CONTEXT_LENGTH)

    @field_validator("text")
    @classmethod
    def text_is_a_word_or_a_short_phrase(cls, value: str) -> str:
        normalized = normalize_text(value)
        if not normalized or len(normalized.split(" ")) > MAX_LOOKUP_WORDS:
            message = f"text must contain 1-{MAX_LOOKUP_WORDS} words"
            raise ValueError(message)
        return value


class AiMeaningsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_sentence: str | None = Field(default=None, max_length=MAX_CONTEXT_LENGTH)


class LexemeResponse(BaseModel):
    id: int
    text: str
    lemma: str
    ipa: str | None
    audio_url: str | None


class MeaningResponse(BaseModel):
    id: int
    part_of_speech: PartOfSpeech
    gloss: str
    translations: list[str]


class RecommendedMeaning(BaseModel):
    meaning_id: int
    contextual_translation: str | None
    confidence: float


class LookupResponse(BaseModel):
    lexeme: LexemeResponse | None
    recommended: RecommendedMeaning | None
    meanings: list[MeaningResponse]
    has_more: bool
    user_meaning_ids: list[int]
    typo_suggestion: str | None
    ai_limited: bool


class MeaningsPage(BaseModel):
    meanings: list[MeaningResponse]
    has_more: bool
