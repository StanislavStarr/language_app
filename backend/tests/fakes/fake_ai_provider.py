from app.integrations.ai.provider import (
    AIError,
    AIResult,
    AIUsage,
    GenerateFallbackMeaningsRequest,
    GenerateMeaningContentRequest,
    SelectSenseRequest,
    TranslateMeaningsRequest,
)
from app.integrations.ai.schemas.fallback_meanings import FallbackMeaningsOutput
from app.integrations.ai.schemas.meaning_content import MeaningContentOutput
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput
from app.integrations.ai.schemas.translations import TranslationsOutput

FAKE_MODEL = "fake-model"
FAKE_PROMPT_VERSION = "fake-v1"


def ai_result[Output](value: Output) -> AIResult[Output]:
    return AIResult(value, AIUsage(10, 5), FAKE_MODEL, FAKE_PROMPT_VERSION)


class FakeAIProvider:
    def __init__(
        self,
        *,
        sense: SenseSelectionOutput | None = None,
        content: MeaningContentOutput | None = None,
        translations: TranslationsOutput | None = None,
        fallback: FallbackMeaningsOutput | None = None,
        error: AIError | None = None,
    ) -> None:
        self._sense = sense
        self._content = content
        self._translations = translations
        self._fallback = fallback
        self._error = error
        self.calls: list[tuple[str, object]] = []

    def _answer[Output](self, name: str, request: object, value: Output | None) -> AIResult[Output]:
        self.calls.append((name, request))
        if self._error is not None:
            raise self._error
        if value is None:
            message = f"FakeAIProvider is not configured for {name}"
            raise AssertionError(message)
        return ai_result(value)

    async def select_sense(self, request: SelectSenseRequest) -> AIResult[SenseSelectionOutput]:
        return self._answer("select_sense", request, self._sense)

    async def generate_meaning_content(
        self, request: GenerateMeaningContentRequest
    ) -> AIResult[MeaningContentOutput]:
        return self._answer("generate_meaning_content", request, self._content)

    async def translate_meanings(
        self, request: TranslateMeaningsRequest
    ) -> AIResult[TranslationsOutput]:
        return self._answer("translate_meanings", request, self._translations)

    async def generate_fallback_meanings(
        self, request: GenerateFallbackMeaningsRequest
    ) -> AIResult[FallbackMeaningsOutput]:
        return self._answer("generate_fallback_meanings", request, self._fallback)
