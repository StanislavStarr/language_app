from dataclasses import dataclass
from typing import Protocol

from app.integrations.ai.schemas.fallback_meanings import FallbackMeaningsOutput
from app.integrations.ai.schemas.meaning_content import MeaningContentOutput
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput
from app.integrations.ai.schemas.translations import MAX_MEANINGS_PER_REQUEST, TranslationsOutput


class AIError(Exception):
    pass


class AIUnavailableError(AIError):
    pass


class AIProviderError(AIError):
    pass


class AIInvalidOutputError(AIProviderError):
    pass


@dataclass(frozen=True, slots=True)
class AIUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class AIResult[Output]:
    value: Output
    usage: AIUsage
    model: str
    prompt_version: str


@dataclass(frozen=True, slots=True)
class SenseCandidate:
    id: int
    part_of_speech: str
    gloss: str


@dataclass(frozen=True, slots=True)
class SelectSenseRequest:
    word: str
    sentence: str
    candidates: tuple[SenseCandidate, ...]


@dataclass(frozen=True, slots=True)
class GenerateMeaningContentRequest:
    word: str
    forms: tuple[str, ...]
    part_of_speech: str
    gloss: str
    cefr_level: str


@dataclass(frozen=True, slots=True)
class TranslateMeaningsRequest:
    word: str
    meanings: tuple[SenseCandidate, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.meanings) <= MAX_MEANINGS_PER_REQUEST:
            message = f"a request needs 1-{MAX_MEANINGS_PER_REQUEST} meanings"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class GenerateFallbackMeaningsRequest:
    word: str
    sentence: str | None


class AIProvider(Protocol):
    async def select_sense(self, request: SelectSenseRequest) -> AIResult[SenseSelectionOutput]: ...

    async def generate_meaning_content(
        self, request: GenerateMeaningContentRequest
    ) -> AIResult[MeaningContentOutput]: ...

    async def translate_meanings(
        self, request: TranslateMeaningsRequest
    ) -> AIResult[TranslationsOutput]: ...

    async def generate_fallback_meanings(
        self, request: GenerateFallbackMeaningsRequest
    ) -> AIResult[FallbackMeaningsOutput]: ...
