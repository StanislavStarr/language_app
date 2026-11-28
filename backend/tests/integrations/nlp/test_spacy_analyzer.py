import asyncio

import pytest
import spacy
from app.integrations.nlp.provider import LemmaCandidate, UniversalPos
from app.integrations.nlp.spacy_analyzer import SpacyTextAnalyzer
from pytest import MonkeyPatch
from spacy.language import Language

APOSTROPHE = "\N{RIGHT SINGLE QUOTATION MARK}"


@pytest.fixture(scope="module")
def analyzer() -> SpacyTextAnalyzer:
    return SpacyTextAnalyzer()


async def lemma_of(
    analyzer: SpacyTextAnalyzer, sentence: str, selected: str
) -> list[LemmaCandidate]:
    start = sentence.index(selected)
    return await analyzer.lemma_candidates(sentence, start, start + len(selected))


@pytest.mark.parametrize(
    ("sentence", "selected", "lemma", "pos"),
    [
        ("He went home.", "went", "go", UniversalPos.VERB),
        ("The books are running late.", "running", "run", UniversalPos.VERB),
        ("The books are running late.", "books", "book", UniversalPos.NOUN),
        ("She bought many books.", "books", "book", UniversalPos.NOUN),
        ("Went there yesterday.", "Went", "go", UniversalPos.VERB),
        ("We visited Paris.", "Paris", "paris", UniversalPos.PROPN),
    ],
)
async def test_lemma_and_part_of_speech_come_from_the_context(
    analyzer: SpacyTextAnalyzer, sentence: str, selected: str, lemma: str, pos: UniversalPos
) -> None:
    assert await lemma_of(analyzer, sentence, selected) == [LemmaCandidate(lemma, pos)]


async def test_saw_is_a_verb_or_a_noun_depending_on_the_sentence(
    analyzer: SpacyTextAnalyzer,
) -> None:
    verb = await lemma_of(analyzer, "I saw him yesterday.", "saw")
    noun = await lemma_of(analyzer, "She bought a rusty saw.", "saw")

    assert verb == [LemmaCandidate("see", UniversalPos.VERB)]
    assert noun == [LemmaCandidate("saw", UniversalPos.NOUN)]


async def test_a_phrase_gets_the_lemma_of_its_first_word(analyzer: SpacyTextAnalyzer) -> None:
    candidates = await lemma_of(analyzer, "She looked forward to it.", "looked forward to")

    assert candidates == [LemmaCandidate("look forward to", UniversalPos.VERB)]


async def test_typographic_apostrophe_is_normalised(analyzer: SpacyTextAnalyzer) -> None:
    phrase = f"didn{APOSTROPHE}t know"
    candidates = await lemma_of(analyzer, f"They {phrase} him.", phrase)

    assert [candidate.lemma for candidate in candidates] == ["don't know"]


@pytest.mark.parametrize(
    ("sentence", "selected", "lemma", "pos"),
    [
        ("He doesn't know.", "doesn't", "do", UniversalPos.AUX),
        ("That is John's car.", "John's", "john", UniversalPos.PROPN),
        ("It is a well-known fact.", "well-known", "well-known", UniversalPos.ADV),
    ],
)
async def test_clitics_do_not_change_the_word_but_hyphenated_compounds_stay_whole(
    analyzer: SpacyTextAnalyzer, sentence: str, selected: str, lemma: str, pos: UniversalPos
) -> None:
    assert await lemma_of(analyzer, sentence, selected) == [LemmaCandidate(lemma, pos)]


async def test_a_partly_selected_word_expands_to_the_whole_token(
    analyzer: SpacyTextAnalyzer,
) -> None:
    sentence = "He went home."

    assert await analyzer.lemma_candidates(sentence, 4, 6) == [
        LemmaCandidate("go", UniversalPos.VERB)
    ]


async def test_sentence_boundaries_ignore_abbreviation_dots(analyzer: SpacyTextAnalyzer) -> None:
    spans = await analyzer.split_sentences("Dr. Brown arrived. Mr. Green left.")

    assert [span.text for span in spans] == ["Dr. Brown arrived.", "Mr. Green left."]


async def test_the_model_is_loaded_once_even_for_concurrent_calls(monkeypatch: MonkeyPatch) -> None:
    loads: list[str] = []
    original_load = spacy.load

    def counting_load(name: str, exclude: list[str]) -> Language:
        loads.append(name)
        return original_load(name, exclude=exclude)

    monkeypatch.setattr(spacy, "load", counting_load)
    fresh = SpacyTextAnalyzer()

    await asyncio.gather(*(fresh.split_sentences(f"Sentence number {n}.") for n in range(8)))

    assert loads == ["en_core_web_sm"]
