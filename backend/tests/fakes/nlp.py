import re
from collections.abc import Mapping

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

ABBREVIATIONS = frozenset({"mr.", "mrs.", "ms.", "dr.", "prof."})
SENTENCE_END = re.compile(r"[.!?]+(?=\s)")
APOSTROPHE = "\N{RIGHT SINGLE QUOTATION MARK}"
WORD = re.compile(f"[A-Za-z{APOSTROPHE}']+")


class FakeTextAnalyzer:
    def __init__(self, lemmas: Mapping[str, tuple[str, UniversalPos]] | None = None) -> None:
        self._lemmas = lemmas or {}

    async def split_sentences(self, text: str) -> list[Span]:
        check_length(text, MAX_TEXT_LENGTH)
        spans: list[Span] = []
        start = 0
        for match in SENTENCE_END.finditer(text):
            last_word = text[start : match.end()].rsplit(maxsplit=1)[-1].lower()
            if last_word in ABBREVIATIONS:
                continue
            spans.append(self._trimmed(text, start, match.end()))
            start = match.end()
        spans.append(self._trimmed(text, start, len(text)))
        return [span for span in spans if span.text]

    async def lemma_candidates(
        self, sentence: str, char_start: int, char_end: int
    ) -> list[LemmaCandidate]:
        check_span(sentence, char_start, char_end)
        check_length(sentence, MAX_SENTENCE_LENGTH)
        words = list(WORD.finditer(sentence, char_start, char_end))
        if not words:
            return []
        first = words[0]
        lemma, pos = self._lemmas.get(first.group().lower(), (first.group(), UniversalPos.NOUN))
        tail = sentence[first.end() : words[-1].end()]
        return [LemmaCandidate(normalize_text(lemma + tail), pos)]

    @staticmethod
    def _trimmed(text: str, start: int, end: int) -> Span:
        raw = text[start:end]
        trimmed_start = start + len(raw) - len(raw.lstrip())
        trimmed_end = start + len(raw.rstrip())
        return Span(trimmed_start, trimmed_end, text[trimmed_start:trimmed_end])
