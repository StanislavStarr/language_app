import re
from dataclasses import dataclass
from typing import Protocol

MAX_LOOKUP_LENGTH = 100
LOOKUP_PATTERN = re.compile(r"[A-Za-z]+(?:[ '.\-][A-Za-z]+)*\.?")


class DictionaryError(Exception):
    pass


class DictionaryUnavailableError(DictionaryError):
    pass


class InvalidDictionaryResponseError(DictionaryError):
    pass


def normalize_lookup(word: str) -> str | None:
    query = word.strip()
    if len(query) > MAX_LOOKUP_LENGTH or not LOOKUP_PATTERN.fullmatch(query):
        return None
    return query


@dataclass(frozen=True, slots=True)
class DictionaryMeaning:
    part_of_speech: str
    definition: str
    example: str | None


@dataclass(frozen=True, slots=True)
class DictionaryEntry:
    word: str
    ipa: str | None
    audio_url: str | None
    meanings: tuple[DictionaryMeaning, ...]


class DictionaryProvider(Protocol):
    async def lookup(self, word: str) -> DictionaryEntry | None: ...
