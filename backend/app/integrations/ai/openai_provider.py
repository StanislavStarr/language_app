import time
from collections.abc import Callable
from dataclasses import dataclass

import openai
import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.integrations.ai.prompts import (
    fallback_meanings,
    meaning_content,
    select_sense,
    translate_meanings,
)
from app.integrations.ai.provider import (
    AIInvalidOutputError,
    AIProviderError,
    AIResult,
    AIUnavailableError,
    AIUsage,
    GenerateFallbackMeaningsRequest,
    GenerateMeaningContentRequest,
    SelectSenseRequest,
    TranslateMeaningsRequest,
)
from app.integrations.ai.schemas.fallback_meanings import (
    FallbackMeaningsOutput,
    check_fallback_meanings,
)
from app.integrations.ai.schemas.meaning_content import MeaningContentOutput, check_meaning_content
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput, check_sense_selection
from app.integrations.ai.schemas.translations import TranslationsOutput, check_translations

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2
MAX_OUTPUT_TOKENS = 600

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class Prompt:
    feature: str
    version: str
    system: str
    user: str


class OpenAIProvider:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIProvider":
        if settings.openai_api_key is None or not settings.openai_model:
            message = "OPENAI_API_KEY and OPENAI_MODEL must be set"
            raise AIProviderError(message)
        client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=MAX_RETRIES,
        )
        return cls(client, settings.openai_model)

    async def select_sense(self, request: SelectSenseRequest) -> AIResult[SenseSelectionOutput]:
        prompt = Prompt(
            feature="select_sense",
            version=select_sense.PROMPT_VERSION,
            system=select_sense.SYSTEM_PROMPT,
            user=select_sense.build_user_prompt(request),
        )
        candidate_ids = frozenset(candidate.id for candidate in request.candidates)
        return await self._run(
            prompt,
            SenseSelectionOutput,
            lambda output: check_sense_selection(output, candidate_ids),
        )

    async def generate_meaning_content(
        self, request: GenerateMeaningContentRequest
    ) -> AIResult[MeaningContentOutput]:
        prompt = Prompt(
            feature="meaning_content",
            version=meaning_content.PROMPT_VERSION,
            system=meaning_content.SYSTEM_PROMPT,
            user=meaning_content.build_user_prompt(request),
        )
        forms = (request.word, *request.forms)
        return await self._run(
            prompt, MeaningContentOutput, lambda output: check_meaning_content(output, forms)
        )

    async def translate_meanings(
        self, request: TranslateMeaningsRequest
    ) -> AIResult[TranslationsOutput]:
        prompt = Prompt(
            feature="translate_meanings",
            version=translate_meanings.PROMPT_VERSION,
            system=translate_meanings.SYSTEM_PROMPT,
            user=translate_meanings.build_user_prompt(request),
        )
        requested_ids = frozenset(meaning.id for meaning in request.meanings)
        return await self._run(
            prompt, TranslationsOutput, lambda output: check_translations(output, requested_ids)
        )

    async def generate_fallback_meanings(
        self, request: GenerateFallbackMeaningsRequest
    ) -> AIResult[FallbackMeaningsOutput]:
        prompt = Prompt(
            feature="fallback_meanings",
            version=fallback_meanings.PROMPT_VERSION,
            system=fallback_meanings.SYSTEM_PROMPT,
            user=fallback_meanings.build_user_prompt(request),
        )
        return await self._run(
            prompt,
            FallbackMeaningsOutput,
            lambda output: check_fallback_meanings(output, request.word),
        )

    async def _run[Output: BaseModel](
        self, prompt: Prompt, schema: type[Output], check: Callable[[Output], None]
    ) -> AIResult[Output]:
        started = time.monotonic()
        usage = AIUsage(0, 0)
        outcome = "error"
        try:
            response = await self._client.responses.parse(
                model=self._model,
                instructions=prompt.system,
                input=prompt.user,
                text_format=schema,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
            )
            if response.usage is not None:
                usage = AIUsage(response.usage.input_tokens, response.usage.output_tokens)
            output = response.output_parsed
            if output is None:
                message = "the model returned no parsable output"
                raise AIInvalidOutputError(message)
            check(output)
            outcome = "ok"
        except (
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.InternalServerError,
        ) as error:
            outcome = "unavailable"
            message = "the AI provider is unavailable"
            raise AIUnavailableError(message) from error
        except (
            openai.LengthFinishReasonError,
            openai.ContentFilterFinishReasonError,
            ValidationError,
            ValueError,
        ) as error:
            outcome = "invalid_output"
            message = "the model output did not pass validation"
            raise AIInvalidOutputError(message) from error
        except openai.OpenAIError as error:
            outcome = "provider_error"
            message = "the AI provider rejected the request"
            raise AIProviderError(message) from error
        except AIInvalidOutputError:
            outcome = "invalid_output"
            raise
        finally:
            logger.info(
                "ai_call",
                feature=prompt.feature,
                model=self._model,
                prompt_version=prompt.version,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                outcome=outcome,
                latency_ms=round((time.monotonic() - started) * 1000),
            )
        return AIResult(output, usage, self._model, prompt.version)
