from collections.abc import Callable

from app.integrations.ai.prompts import (
    fallback_meanings,
    meaning_content,
    select_sense,
    translate_meanings,
)
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


type Answer[Request, Output] = Output | Callable[[Request], Output]


def ai_result[Output](value: Output, prompt_version: str) -> AIResult[Output]:
    return AIResult(value, AIUsage(10, 5), FAKE_MODEL, prompt_version)


class FakeAIProvider:
    def __init__(
        self,
        *,
        sense: Answer[SelectSenseRequest, SenseSelectionOutput] | None = None,
        content: Answer[GenerateMeaningContentRequest, MeaningContentOutput] | None = None,
        translations: Answer[TranslateMeaningsRequest, TranslationsOutput] | None = None,
        fallback: Answer[GenerateFallbackMeaningsRequest, FallbackMeaningsOutput] | None = None,
        error: AIError | None = None,
    ) -> None:
        self._sense = sense
        self._content = content
        self._translations = translations
        self._fallback = fallback
        self._error = error
        self.calls: list[tuple[str, object]] = []

    def _answer[Request, Output](
        self,
        name: str,
        prompt_version: str,
        request: Request,
        answer: Answer[Request, Output] | None,
    ) -> AIResult[Output]:
        self.calls.append((name, request))
        if self._error is not None:
            raise self._error
        if answer is None:
            message = f"FakeAIProvider is not configured for {name}"
            raise AssertionError(message)
        return ai_result(answer(request) if callable(answer) else answer, prompt_version)

    async def select_sense(self, request: SelectSenseRequest) -> AIResult[SenseSelectionOutput]:
        return self._answer("select_sense", select_sense.PROMPT_VERSION, request, self._sense)

    async def generate_meaning_content(
        self, request: GenerateMeaningContentRequest
    ) -> AIResult[MeaningContentOutput]:
        return self._answer(
            "generate_meaning_content", meaning_content.PROMPT_VERSION, request, self._content
        )

    async def translate_meanings(
        self, request: TranslateMeaningsRequest
    ) -> AIResult[TranslationsOutput]:
        return self._answer(
            "translate_meanings", translate_meanings.PROMPT_VERSION, request, self._translations
        )

    async def generate_fallback_meanings(
        self, request: GenerateFallbackMeaningsRequest
    ) -> AIResult[FallbackMeaningsOutput]:
        return self._answer(
            "generate_fallback_meanings", fallback_meanings.PROMPT_VERSION, request, self._fallback
        )
