import asyncio
import time
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.integrations.dictionary.provider import (
    DictionaryEntry,
    DictionaryMeaning,
    DictionaryUnavailableError,
    InvalidDictionaryResponseError,
    normalize_lookup,
)

BASE_URL = "https://api.dictionaryapi.dev/api/v2/entries/en"
REQUEST_TIMEOUT_SECONDS = 5.0
MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.5
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_BODY_BYTES = 1_000_000
MAX_TEXT_LENGTH = 1_000
MAX_MEANINGS = 50
PREFERRED_AUDIO_MARKER = "-us."

logger = structlog.get_logger()


class FreeDictionaryModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class FreeDictionaryPhonetic(FreeDictionaryModel):
    text: str | None = None
    audio: str | None = None


class FreeDictionaryDefinition(FreeDictionaryModel):
    definition: str = ""
    example: str | None = None


class FreeDictionaryMeaning(FreeDictionaryModel):
    part_of_speech: str = Field(default="", alias="partOfSpeech")
    definitions: list[FreeDictionaryDefinition] = Field(default_factory=list)


class FreeDictionaryEntry(FreeDictionaryModel):
    phonetic: str | None = None
    phonetics: list[FreeDictionaryPhonetic] = Field(default_factory=list)
    meanings: list[FreeDictionaryMeaning] = Field(default_factory=list)


@dataclass(slots=True)
class LookupTrace:
    attempts: int = 0
    outcome: str = "unavailable"


def usable_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text if text and len(text) <= MAX_TEXT_LENGTH else None


def usable_audio(value: str | None) -> str | None:
    url = usable_text(value)
    parsed = urlparse(url) if url else None
    return url if parsed and parsed.scheme == "https" and parsed.netloc else None


def pick_audio(entries: list[FreeDictionaryEntry]) -> str | None:
    urls = [
        url
        for entry in entries
        for phonetic in entry.phonetics
        if (url := usable_audio(phonetic.audio))
    ]
    preferred = [url for url in urls if PREFERRED_AUDIO_MARKER in url]
    return next(iter(preferred or urls), None)


def pick_ipa(entries: list[FreeDictionaryEntry]) -> str | None:
    candidates = [entry.phonetic for entry in entries] + [
        phonetic.text for entry in entries for phonetic in entry.phonetics
    ]
    return next((text for value in candidates if (text := usable_text(value))), None)


def collect_meanings(entries: list[FreeDictionaryEntry]) -> tuple[DictionaryMeaning, ...]:
    meanings: list[DictionaryMeaning] = []
    for entry in entries:
        for meaning in entry.meanings:
            part_of_speech = meaning.part_of_speech.strip().lower()
            for definition in meaning.definitions:
                text = usable_text(definition.definition)
                if part_of_speech and text:
                    meanings.append(
                        DictionaryMeaning(part_of_speech, text, usable_text(definition.example))
                    )
                if len(meanings) >= MAX_MEANINGS:
                    return tuple(meanings)
    return tuple(meanings)


def parse_entries(payload: object) -> list[FreeDictionaryEntry]:
    if not isinstance(payload, list) or not payload:
        message = "expected a non-empty list of entries"
        raise InvalidDictionaryResponseError(message)
    entries: list[FreeDictionaryEntry] = []
    for item in payload:
        try:
            entries.append(FreeDictionaryEntry.model_validate(item))
        except ValidationError:
            continue
    if not entries:
        message = "no entry matches the expected shape"
        raise InvalidDictionaryResponseError(message)
    return entries


def to_dictionary_entry(word: str, entries: list[FreeDictionaryEntry]) -> DictionaryEntry | None:
    meanings = collect_meanings(entries)
    if not meanings:
        return None
    return DictionaryEntry(word, pick_ipa(entries), pick_audio(entries), meanings)


class FreeDictionaryProvider:
    def __init__(
        self, client: httpx.AsyncClient, retry_delay_seconds: float = RETRY_DELAY_SECONDS
    ) -> None:
        self._client = client
        self._retry_delay_seconds = retry_delay_seconds

    async def lookup(self, word: str) -> DictionaryEntry | None:
        query = normalize_lookup(word)
        if query is None:
            return None
        trace = LookupTrace()
        started = time.monotonic()
        try:
            entry = await self._fetch(query, trace)
        except InvalidDictionaryResponseError:
            trace.outcome = "invalid_response"
            raise
        except DictionaryUnavailableError:
            trace.outcome = "unavailable"
            raise
        else:
            trace.outcome = "found" if entry is not None else "not_found"
            return entry
        finally:
            logger.info(
                "dictionary_lookup",
                provider="free_dictionary",
                operation="lookup",
                outcome=trace.outcome,
                attempts=trace.attempts,
                latency_ms=round((time.monotonic() - started) * 1000),
            )

    async def _fetch(self, query: str, trace: LookupTrace) -> DictionaryEntry | None:
        url = f"{BASE_URL}/{quote(query, safe='')}"
        for attempt in range(MAX_ATTEMPTS):
            trace.attempts = attempt + 1
            status, body = await self._request(url)
            if status == httpx.codes.NOT_FOUND:
                return None
            if status is not None and httpx.codes.is_success(status):
                return self._parse(query, body)
            if attempt == MAX_ATTEMPTS - 1 or status not in (None, *RETRYABLE_STATUSES):
                break
            await asyncio.sleep(self._retry_delay_seconds)
        message = "dictionary request failed"
        raise DictionaryUnavailableError(message)

    async def _request(self, url: str) -> tuple[int | None, bytes]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                async with self._client.stream(
                    "GET", url, timeout=REQUEST_TIMEOUT_SECONDS
                ) as response:
                    if not response.is_success:
                        return response.status_code, b""
                    return response.status_code, await self._read_limited(response)
        except (httpx.TransportError, TimeoutError):
            return None, b""
        except httpx.HTTPError as error:
            message = "dictionary request failed"
            raise DictionaryUnavailableError(message) from error

    @staticmethod
    async def _read_limited(response: httpx.Response) -> bytes:
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                message = "response body is too large"
                raise InvalidDictionaryResponseError(message)
        return bytes(body)

    @staticmethod
    def _parse(query: str, body: bytes) -> DictionaryEntry | None:
        try:
            payload = httpx.Response(200, content=body).json()
        except ValueError as error:
            message = "response is not valid JSON"
            raise InvalidDictionaryResponseError(message) from error
        return to_dictionary_entry(query, parse_entries(payload))
