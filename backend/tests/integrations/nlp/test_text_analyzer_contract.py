import itertools

import pytest
from app.integrations.nlp.provider import (
    MAX_SENTENCE_LENGTH,
    MAX_TEXT_LENGTH,
    InvalidSpanError,
    TextAnalyzer,
    TextTooLongError,
)
from app.integrations.nlp.spacy_analyzer import SpacyTextAnalyzer

from tests.fakes.nlp import FakeTextAnalyzer


@pytest.fixture(scope="module")
def spacy_analyzer() -> SpacyTextAnalyzer:
    return SpacyTextAnalyzer()


@pytest.fixture(params=["spacy", "fake"])
def analyzer(request: pytest.FixtureRequest, spacy_analyzer: SpacyTextAnalyzer) -> TextAnalyzer:
    if request.param == "spacy":
        return spacy_analyzer
    return FakeTextAnalyzer()


TEXT = "  Mr. Smith met Dr. Jones.  They talked!\n\nThen they left.  "


async def test_sentence_spans_point_into_the_original_text(analyzer: TextAnalyzer) -> None:
    spans = await analyzer.split_sentences(TEXT)

    assert [span.text for span in spans] == [
        "Mr. Smith met Dr. Jones.",
        "They talked!",
        "Then they left.",
    ]
    assert all(TEXT[span.start : span.end] == span.text for span in spans)
    assert all(first.end <= second.start for first, second in itertools.pairwise(spans))


async def test_blank_text_has_no_sentences(analyzer: TextAnalyzer) -> None:
    assert await analyzer.split_sentences("") == []
    assert await analyzer.split_sentences("  \n\t ") == []


@pytest.mark.parametrize(("start", "end"), [(-1, 3), (3, 3), (5, 3), (0, 99)])
async def test_invalid_span_is_rejected(analyzer: TextAnalyzer, start: int, end: int) -> None:
    with pytest.raises(InvalidSpanError):
        await analyzer.lemma_candidates("He went home.", start, end)


async def test_punctuation_has_no_lemma_candidates(analyzer: TextAnalyzer) -> None:
    assert await analyzer.lemma_candidates("He went home.", 12, 13) == []


async def test_text_above_the_size_limit_is_rejected(analyzer: TextAnalyzer) -> None:
    with pytest.raises(TextTooLongError):
        await analyzer.split_sentences("a" * (MAX_TEXT_LENGTH + 1))


async def test_sentence_above_the_size_limit_is_rejected(analyzer: TextAnalyzer) -> None:
    with pytest.raises(TextTooLongError):
        await analyzer.lemma_candidates("a" * (MAX_SENTENCE_LENGTH + 1), 0, 1)
