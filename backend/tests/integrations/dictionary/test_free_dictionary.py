from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from app.integrations.dictionary.free_dictionary import (
    BASE_URL,
    MAX_ATTEMPTS,
    MAX_BODY_BYTES,
    MAX_MEANINGS,
    REQUEST_TIMEOUT_SECONDS,
    FreeDictionaryProvider,
)
from app.integrations.dictionary.provider import (
    DictionaryEntry,
    DictionaryMeaning,
    DictionaryUnavailableError,
    InvalidDictionaryResponseError,
)
from structlog.testing import capture_logs

BANK = [
    {
        "word": "bank",
        "phonetic": "/bæŋk/",
        "phonetics": [
            {"text": "/bæŋk/", "audio": "https://example.org/media/bank-uk.mp3"},
            {"text": "/bæŋk/", "audio": "https://example.org/media/bank-us.mp3"},
        ],
        "meanings": [
            {
                "partOfSpeech": "noun",
                "definitions": [
                    {"definition": "An institution for money.", "example": "She went to the bank."},
                    {"definition": "The land beside a river."},
                ],
            },
            {"partOfSpeech": "Verb", "definitions": [{"definition": "To tilt."}]},
        ],
        "license": {"name": "CC BY-SA 3.0"},
    },
    {
        "word": "bank",
        "phonetics": [],
        "meanings": [{"partOfSpeech": "noun", "definitions": [{"definition": "A row of items."}]}],
    },
]


@pytest.fixture
async def provider() -> AsyncIterator[FreeDictionaryProvider]:
    async with httpx.AsyncClient() as client:
        yield FreeDictionaryProvider(client, retry_delay_seconds=0)


def url(word: str) -> str:
    return f"{BASE_URL}/{word}"


@respx.mock
async def test_found_word_is_normalised(provider: FreeDictionaryProvider) -> None:
    respx.get(url("bank")).respond(json=BANK)

    entry = await provider.lookup("bank")

    assert entry == DictionaryEntry(
        word="bank",
        ipa="/bæŋk/",
        audio_url="https://example.org/media/bank-us.mp3",
        meanings=(
            DictionaryMeaning("noun", "An institution for money.", "She went to the bank."),
            DictionaryMeaning("noun", "The land beside a river.", None),
            DictionaryMeaning("verb", "To tilt.", None),
            DictionaryMeaning("noun", "A row of items.", None),
        ),
    )


@respx.mock
async def test_unknown_word_returns_none_without_retrying(provider: FreeDictionaryProvider) -> None:
    route = respx.get(url("zzqqxx")).respond(
        404, json={"title": "No Definitions Found", "message": "Sorry"}
    )

    assert await provider.lookup("zzqqxx") is None
    assert route.call_count == 1


@respx.mock
async def test_timeout_is_retried_once_and_then_reported(provider: FreeDictionaryProvider) -> None:
    route = respx.get(url("bank")).mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(DictionaryUnavailableError):
        await provider.lookup("bank")

    assert route.call_count == MAX_ATTEMPTS


@respx.mock
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_temporary_failure_is_retried(provider: FreeDictionaryProvider, status: int) -> None:
    route = respx.get(url("bank")).mock(
        side_effect=[httpx.Response(status), httpx.Response(200, json=BANK)]
    )

    entry = await provider.lookup("bank")

    assert entry is not None
    assert route.call_count == 2


@respx.mock
async def test_persistent_server_error_is_reported(provider: FreeDictionaryProvider) -> None:
    route = respx.get(url("bank")).respond(503)

    with pytest.raises(DictionaryUnavailableError):
        await provider.lookup("bank")

    assert route.call_count == MAX_ATTEMPTS


@respx.mock
async def test_other_client_errors_are_not_retried(provider: FreeDictionaryProvider) -> None:
    route = respx.get(url("bank")).respond(400)

    with pytest.raises(DictionaryUnavailableError):
        await provider.lookup("bank")

    assert route.call_count == 1


@respx.mock
@pytest.mark.parametrize(
    "body",
    [
        b"<html>not json</html>",
        b'{"title": "unexpected object"}',
        b"[]",
        b'["a string"]',
        b'[{"word": "bank", "meanings": "oops"}]',
        b'[{"word": "bank", "meanings": [{"partOfSpeech": null}]}]',
    ],
)
async def test_garbage_response_is_rejected(provider: FreeDictionaryProvider, body: bytes) -> None:
    respx.get(url("bank")).respond(200, content=body)

    with pytest.raises(InvalidDictionaryResponseError):
        await provider.lookup("bank")


@respx.mock
async def test_unusable_fields_are_dropped_not_trusted(provider: FreeDictionaryProvider) -> None:
    payload = [
        {
            "word": "bank",
            "phonetic": "x" * 2_000,
            "phonetics": [{"text": "/bæŋk/", "audio": "http://insecure.example/bank.mp3"}],
            "meanings": [
                {
                    "partOfSpeech": "noun",
                    "definitions": [{"definition": "y" * 2_000}, {"definition": "Fine."}],
                },
                {"partOfSpeech": "", "definitions": [{"definition": "No part of speech."}]},
            ],
        }
    ]
    respx.get(url("bank")).respond(json=payload)

    entry = await provider.lookup("bank")

    assert entry is not None
    assert entry.audio_url is None
    assert entry.ipa == "/bæŋk/"
    assert [meaning.definition for meaning in entry.meanings] == ["Fine."]


@respx.mock
async def test_number_of_meanings_is_bounded(provider: FreeDictionaryProvider) -> None:
    definitions = [{"definition": f"Meaning {number}."} for number in range(MAX_MEANINGS + 20)]
    respx.get(url("bank")).respond(
        json=[{"word": "bank", "meanings": [{"partOfSpeech": "noun", "definitions": definitions}]}]
    )

    entry = await provider.lookup("bank")

    assert entry is not None
    assert len(entry.meanings) == MAX_MEANINGS


@respx.mock
async def test_phrase_is_url_encoded(provider: FreeDictionaryProvider) -> None:
    route = respx.get(url("look%20forward%20to")).respond(json=BANK)

    assert await provider.lookup("  look forward to ") is not None
    assert route.called


@respx.mock
async def test_request_uses_the_five_second_timeout(provider: FreeDictionaryProvider) -> None:
    route = respx.get(url("bank")).respond(json=BANK)

    await provider.lookup("bank")

    timeout = route.calls.last.request.extensions["timeout"]
    assert timeout == {
        "connect": REQUEST_TIMEOUT_SECONDS,
        "read": REQUEST_TIMEOUT_SECONDS,
        "write": REQUEST_TIMEOUT_SECONDS,
        "pool": REQUEST_TIMEOUT_SECONDS,
    }


@respx.mock
@pytest.mark.parametrize(
    "word", ["", "   ", "w" * 101, "..", ".", "a/b", "a?b#c", "100%", "x\ny", "caf\u00e9", "-bank"]
)
async def test_invalid_lookup_text_does_not_reach_the_network(
    provider: FreeDictionaryProvider, word: str
) -> None:
    route = respx.get(url("bank")).respond(json=BANK)

    assert await provider.lookup(word) is None
    assert not route.called


@respx.mock
async def test_entry_without_usable_definitions_means_no_data(
    provider: FreeDictionaryProvider,
) -> None:
    respx.get(url("bank")).respond(json=[{"word": "bank", "meanings": []}])

    assert await provider.lookup("bank") is None


@respx.mock
async def test_one_malformed_entry_does_not_discard_the_valid_ones(
    provider: FreeDictionaryProvider,
) -> None:
    payload = [{"word": "bank", "meanings": "oops"}, *BANK]
    respx.get(url("bank")).respond(json=payload)

    entry = await provider.lookup("bank")

    assert entry is not None
    assert len(entry.meanings) == 4


@respx.mock
@pytest.mark.parametrize(
    "failure", [httpx.ConnectError("refused"), httpx.RemoteProtocolError("broken")]
)
async def test_transport_failure_is_retried_then_reported(
    provider: FreeDictionaryProvider, failure: httpx.TransportError
) -> None:
    route = respx.get(url("bank")).mock(side_effect=failure)

    with pytest.raises(DictionaryUnavailableError):
        await provider.lookup("bank")

    assert route.call_count == MAX_ATTEMPTS


@respx.mock
async def test_other_http_errors_are_reported_without_retry(
    provider: FreeDictionaryProvider,
) -> None:
    route = respx.get(url("bank")).mock(side_effect=httpx.DecodingError("bad gzip"))

    with pytest.raises(DictionaryUnavailableError):
        await provider.lookup("bank")

    assert route.call_count == 1


@respx.mock
async def test_redirect_is_not_followed_or_trusted(provider: FreeDictionaryProvider) -> None:
    route = respx.get(url("bank")).respond(302, headers={"Location": "https://evil.example/"})

    with pytest.raises(DictionaryUnavailableError):
        await provider.lookup("bank")

    assert route.call_count == 1


@respx.mock
async def test_oversized_response_is_rejected(provider: FreeDictionaryProvider) -> None:
    respx.get(url("bank")).respond(200, content=b"[" + b" " * MAX_BODY_BYTES + b"]")

    with pytest.raises(InvalidDictionaryResponseError):
        await provider.lookup("bank")


@respx.mock
async def test_only_https_audio_is_used_and_the_us_variant_is_preferred(
    provider: FreeDictionaryProvider,
) -> None:
    payload = [
        {
            "word": "bank",
            "phonetics": [
                {"audio": "http://insecure.example/bank-us.mp3"},
                {"audio": "https://example.org/bank-uk.mp3"},
            ],
            "meanings": [{"partOfSpeech": "noun", "definitions": [{"definition": "A bank."}]}],
        }
    ]
    respx.get(url("bank")).respond(json=payload)

    entry = await provider.lookup("bank")

    assert entry is not None
    assert entry.audio_url == "https://example.org/bank-uk.mp3"


@respx.mock
async def test_log_describes_the_lookup_without_the_word(provider: FreeDictionaryProvider) -> None:
    respx.get(url("secretword")).respond(404)

    with capture_logs() as logs:
        await provider.lookup("secretword")

    assert logs == [
        {
            "event": "dictionary_lookup",
            "log_level": "info",
            "provider": "free_dictionary",
            "operation": "lookup",
            "outcome": "not_found",
            "attempts": 1,
            "latency_ms": logs[0]["latency_ms"],
        }
    ]
    assert "secretword" not in str(logs)


@respx.mock
async def test_log_tells_failures_apart(provider: FreeDictionaryProvider) -> None:
    respx.get(url("bank")).respond(503)
    respx.get(url("junk")).respond(200, content=b"nope")

    with capture_logs() as logs:
        for word in ("bank", "junk"):
            with pytest.raises(Exception):  # noqa: B017
                await provider.lookup(word)

    assert [(entry["outcome"], entry["attempts"]) for entry in logs] == [
        ("unavailable", MAX_ATTEMPTS),
        ("invalid_response", 1),
    ]
