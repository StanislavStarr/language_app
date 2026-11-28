from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class UniversalPos(StrEnum):
    ADJ = "ADJ"
    ADP = "ADP"
    ADV = "ADV"
    AUX = "AUX"
    CCONJ = "CCONJ"
    DET = "DET"
    INTJ = "INTJ"
    NOUN = "NOUN"
    NUM = "NUM"
    PART = "PART"
    PRON = "PRON"
    PROPN = "PROPN"
    PUNCT = "PUNCT"
    SCONJ = "SCONJ"
    SYM = "SYM"
    VERB = "VERB"
    X = "X"


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class LemmaCandidate:
    lemma: str
    pos: UniversalPos


MAX_TEXT_LENGTH = 20_000
MAX_SENTENCE_LENGTH = 2_000


class NlpError(Exception):
    pass


class InvalidSpanError(NlpError):
    pass


class TextTooLongError(NlpError):
    pass


def check_length(text: str, limit: int) -> None:
    if len(text) > limit:
        message = f"text of {len(text)} chars exceeds the limit of {limit}"
        raise TextTooLongError(message)


def check_span(sentence: str, char_start: int, char_end: int) -> None:
    if not 0 <= char_start < char_end <= len(sentence):
        message = f"invalid span {char_start}:{char_end} for a sentence of {len(sentence)} chars"
        raise InvalidSpanError(message)


class TextAnalyzer(Protocol):
    async def split_sentences(self, text: str) -> list[Span]: ...

    async def lemma_candidates(
        self, sentence: str, char_start: int, char_end: int
    ) -> list[LemmaCandidate]: ...
