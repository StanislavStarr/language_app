import asyncio
import re
import threading

import spacy
from spacy.language import Language
from spacy.tokens import Doc, Token

from app.integrations.nlp.normalization import normalize_text
from app.integrations.nlp.provider import (
    MAX_SENTENCE_LENGTH,
    MAX_TEXT_LENGTH,
    LemmaCandidate,
    Span,
    UniversalPos,
    check_length,
    check_span,
)

COMPOUND_SEPARATORS = re.compile(r"[\s-]")
MODEL_NAME = "en_core_web_sm"
EXCLUDED_COMPONENTS = ["ner", "parser"]
ENABLED_COMPONENTS = ["senter"]


def is_word(token: Token) -> bool:
    return not (token.is_space or token.is_punct)


def to_pos(token: Token) -> UniversalPos:
    try:
        return UniversalPos(token.pos_)
    except ValueError:
        return UniversalPos.X


class SpacyTextAnalyzer:
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._model_name = model_name
        self._pipeline: Language | None = None
        self._lock = threading.Lock()

    def _process(self, text: str) -> Doc:
        with self._lock:
            if self._pipeline is None:
                pipeline = spacy.load(self._model_name, exclude=EXCLUDED_COMPONENTS)
                for component in ENABLED_COMPONENTS:
                    pipeline.enable_pipe(component)
                self._pipeline = pipeline
            return self._pipeline(text)

    def _split_sentences(self, text: str) -> list[Span]:
        check_length(text, MAX_TEXT_LENGTH)
        spans: list[Span] = []
        for sentence in self._process(text).sents:
            raw = text[sentence.start_char : sentence.end_char]
            start = sentence.start_char + len(raw) - len(raw.lstrip())
            end = sentence.start_char + len(raw.rstrip())
            if start < end:
                spans.append(Span(start, end, text[start:end]))
        return spans

    def _lemma_candidates(
        self, sentence: str, char_start: int, char_end: int
    ) -> list[LemmaCandidate]:
        check_length(sentence, MAX_SENTENCE_LENGTH)
        check_span(sentence, char_start, char_end)
        span = self._process(sentence).char_span(char_start, char_end, alignment_mode="expand")
        words = [token for token in span if is_word(token)] if span is not None else []
        if not words:
            return []
        first = words[0]
        if not COMPOUND_SEPARATORS.search(sentence[char_start:char_end]):
            return [LemmaCandidate(normalize_text(first.lemma_), to_pos(first))]
        tail = sentence[first.idx + len(first.text) : words[-1].idx + len(words[-1].text)]
        return [LemmaCandidate(normalize_text(first.lemma_ + tail), to_pos(first))]

    async def split_sentences(self, text: str) -> list[Span]:
        return await asyncio.to_thread(self._split_sentences, text)

    async def lemma_candidates(
        self, sentence: str, char_start: int, char_end: int
    ) -> list[LemmaCandidate]:
        return await asyncio.to_thread(self._lemma_candidates, sentence, char_start, char_end)
