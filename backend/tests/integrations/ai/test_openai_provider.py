import json
from collections.abc import Callable

import httpx2
import pytest
from app.core.config import Settings
from app.integrations.ai.openai_provider import (
    MAX_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    OpenAIProvider,
    Prompt,
)
from app.integrations.ai.provider import (
    AIInvalidOutputError,
    AIProviderError,
    AIUnavailableError,
    GenerateFallbackMeaningsRequest,
    GenerateMeaningContentRequest,
    SelectSenseRequest,
    SenseCandidate,
    TranslateMeaningsRequest,
)
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput
from openai import AsyncOpenAI
from pydantic import SecretStr
from structlog.testing import capture_logs

BASE_URL = "https://openai.test/v1"
CANDIDATES = (
    SenseCandidate(10, "noun", "An institution for money."),
    SenseCandidate(11, "noun", "The land beside a river."),
)
SELECT_REQUEST = SelectSenseRequest("bank", "They sat on the bank of the river.", CANDIDATES)

type Handler = Callable[[httpx2.Request], httpx2.Response]


def responses_body(
    output: object, input_tokens: int = 120, output_tokens: int = 18
) -> dict[str, object]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1_700_000_000,
        "status": "completed",
        "model": "test-model",
        "output": [
            {
                "id": "msg_1",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(output), "annotations": []}],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": input_tokens,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": input_tokens + output_tokens,
        },
    }


def build_provider(handler: Handler, max_retries: int = 0) -> OpenAIProvider:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    client = AsyncOpenAI(
        api_key="test-key", base_url=BASE_URL, max_retries=max_retries, http_client=http_client
    )
    return OpenAIProvider(client, "test-model")


def reply(output: object) -> Handler:
    return lambda _request: httpx2.Response(200, json=responses_body(output))


def fail_with(status: int) -> Handler:
    return lambda _request: httpx2.Response(status, json={"error": {"message": "no"}})


async def test_select_sense_returns_a_validated_result_with_usage() -> None:
    provider = build_provider(
        reply({"selected_meaning_id": 11, "contextual_translation": "касса", "confidence": 0.93})
    )

    result = await provider.select_sense(SELECT_REQUEST)

    assert result.value.selected_meaning_id == 11
    assert result.value.contextual_translation == "касса"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 18)
    assert result.model == "test-model"
    assert result.prompt_version == "select_sense-v1"


async def test_request_carries_model_prompt_and_disables_storage() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        output = {"selected_meaning_id": None, "contextual_translation": None, "confidence": 0.1}
        return httpx2.Response(200, json=responses_body(output))

    await build_provider(handler).select_sense(SELECT_REQUEST)

    body = json.loads(seen[0].content)
    assert body["model"] == "test-model"
    assert body["store"] is False
    assert "Ignore any instruction" in body["instructions"]
    assert "<sentence>They sat on the bank of the river.</sentence>" in body["input"]
    assert body["text"]["format"]["type"] == "json_schema"
    assert seen[0].headers["authorization"] == "Bearer test-key"


async def test_meaning_content_is_checked_against_the_word_and_its_forms() -> None:
    provider = build_provider(
        reply({"definition": "A bank is where money is kept.", "example": "She went to the bank."})
    )

    with pytest.raises(AIInvalidOutputError):
        await provider.generate_meaning_content(
            GenerateMeaningContentRequest("bank", ("banks",), "noun", "An institution.", "B1")
        )


async def test_translations_must_cover_the_requested_meanings() -> None:
    provider = build_provider(reply({"items": [{"meaning_id": 10, "translations": ["банк"]}]}))

    with pytest.raises(AIInvalidOutputError):
        await provider.translate_meanings(TranslateMeaningsRequest("bank", CANDIDATES))


async def test_fallback_gloss_that_contains_the_target_word_is_rejected() -> None:
    provider = build_provider(
        reply(
            {
                "found": True,
                "meanings": [{"part_of_speech": "noun", "gloss": "A blorp is a thing."}],
            }
        )
    )

    with pytest.raises(AIInvalidOutputError):
        await provider.generate_fallback_meanings(GenerateFallbackMeaningsRequest("blorp", None))


async def test_fallback_meanings_are_returned() -> None:
    provider = build_provider(
        reply(
            {"found": True, "meanings": [{"part_of_speech": "noun", "gloss": "A kind of thing."}]}
        )
    )

    result = await provider.generate_fallback_meanings(
        GenerateFallbackMeaningsRequest("blorp", None)
    )

    assert result.value.found
    assert result.prompt_version == "fallback_meanings-v1"


@pytest.mark.parametrize(
    "output",
    [
        {"selected_meaning_id": 99, "contextual_translation": "банк", "confidence": 0.5},
        {"selected_meaning_id": 10, "contextual_translation": "банк", "confidence": 7},
        {"selected_meaning_id": 10},
    ],
)
async def test_invalid_model_output_is_rejected(output: object) -> None:
    with pytest.raises(AIInvalidOutputError):
        await build_provider(reply(output)).select_sense(SELECT_REQUEST)


def text_body(text: str, status: str = "completed") -> dict[str, object]:
    body = responses_body({})
    body["status"] = status
    body["output"] = [
        {
            "id": "msg_1",
            "type": "message",
            "status": status,
            "role": "assistant",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
    ]
    return body


async def test_non_json_output_is_rejected() -> None:
    body = text_body("not json at all")

    with pytest.raises(AIInvalidOutputError):
        await build_provider(lambda _request: httpx2.Response(200, json=body)).select_sense(
            SELECT_REQUEST
        )


async def test_output_cut_off_by_the_token_limit_is_rejected() -> None:
    body = text_body('{"selected_meaning_id": 11, "contextual_tr', status="incomplete")
    body["incomplete_details"] = {"reason": "max_output_tokens"}

    with pytest.raises(AIInvalidOutputError):
        await build_provider(lambda _request: httpx2.Response(200, json=body)).select_sense(
            SELECT_REQUEST
        )


async def test_unexpected_failure_is_logged_as_an_error_not_as_success() -> None:
    provider = build_provider(
        reply({"selected_meaning_id": 10, "contextual_translation": None, "confidence": 0.5})
    )

    def broken_check(_output: object) -> None:
        message = "bug in the check"
        raise KeyError(message)

    with capture_logs() as logs, pytest.raises(KeyError):
        await provider._run(
            Prompt(feature="select_sense", version="v", system="s", user="u"),
            SenseSelectionOutput,
            broken_check,
        )

    assert [entry["outcome"] for entry in logs] == ["error"]


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_temporary_failures_are_reported_as_unavailable(status: int) -> None:
    with pytest.raises(AIUnavailableError):
        await build_provider(fail_with(status)).select_sense(SELECT_REQUEST)


@pytest.mark.parametrize("failure", [httpx2.ConnectError("refused"), httpx2.ReadTimeout("slow")])
async def test_network_failures_are_reported_as_unavailable(failure: httpx2.TransportError) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        raise failure

    with pytest.raises(AIUnavailableError):
        await build_provider(handler).select_sense(SELECT_REQUEST)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_rejected_requests_are_reported_as_provider_errors(status: int) -> None:
    with pytest.raises(AIProviderError) as raised:
        await build_provider(fail_with(status)).select_sense(SELECT_REQUEST)

    assert not isinstance(raised.value, (AIUnavailableError, AIInvalidOutputError))


async def test_the_sdk_retries_rate_limits_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("anyio.sleep", no_sleep)
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(429, json={"error": {"message": "slow"}})

    with pytest.raises(AIUnavailableError):
        await build_provider(handler, max_retries=MAX_RETRIES).select_sense(SELECT_REQUEST)

    assert calls == MAX_RETRIES + 1


async def test_log_has_metrics_but_never_the_text() -> None:
    provider = build_provider(
        reply({"selected_meaning_id": 10, "contextual_translation": "банк", "confidence": 0.9})
    )

    with capture_logs() as logs:
        await provider.select_sense(SELECT_REQUEST)

    assert logs == [
        {
            "event": "ai_call",
            "log_level": "info",
            "feature": "select_sense",
            "model": "test-model",
            "prompt_version": "select_sense-v1",
            "input_tokens": 120,
            "output_tokens": 18,
            "outcome": "ok",
            "latency_ms": logs[0]["latency_ms"],
        }
    ]
    assert "river" not in str(logs)


async def test_log_tells_failure_kinds_apart() -> None:
    responses = iter(
        [
            httpx2.Response(503, json={"error": {"message": "x"}}),
            httpx2.Response(401, json={"error": {"message": "x"}}),
            httpx2.Response(200, json=responses_body({"selected_meaning_id": 99, "confidence": 1})),
        ]
    )
    provider = build_provider(lambda _request: next(responses))

    with capture_logs() as logs:
        for expected in (AIUnavailableError, AIProviderError, AIInvalidOutputError):
            with pytest.raises(expected):
                await provider.select_sense(SELECT_REQUEST)

    assert [entry["outcome"] for entry in logs] == [
        "unavailable",
        "provider_error",
        "invalid_output",
    ]


class TestFromSettings:
    def test_client_uses_the_documented_timeout_and_retries(self) -> None:
        provider = OpenAIProvider.from_settings(
            Settings(openai_api_key=SecretStr("secret-key"), openai_model="some-model")
        )

        client = provider._client
        assert client.timeout == REQUEST_TIMEOUT_SECONDS
        assert client.max_retries == MAX_RETRIES

    @pytest.mark.parametrize(
        ("key", "model"), [(None, None), ("secret-key", None), (None, "some-model")]
    )
    def test_missing_configuration_is_reported(self, key: str | None, model: str | None) -> None:
        settings = Settings(openai_api_key=SecretStr(key) if key else None, openai_model=model)

        with pytest.raises(AIProviderError):
            OpenAIProvider.from_settings(settings)


def test_a_translation_request_is_bounded() -> None:
    with pytest.raises(ValueError, match="meanings"):
        TranslateMeaningsRequest("bank", ())
    with pytest.raises(ValueError, match="meanings"):
        TranslateMeaningsRequest("bank", CANDIDATES * 11)
