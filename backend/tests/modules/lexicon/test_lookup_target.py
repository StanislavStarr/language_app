from app.integrations.nlp.provider import LemmaCandidate, NlpError, Span, UniversalPos
from app.modules.lexicon.enums import LexemeType, PartOfSpeech
from app.modules.lexicon.lookup_target import build_target, locate
from tests.fakes.nlp import FakeTextAnalyzer


class BrokenAnalyzer:
    async def split_sentences(self, _text: str) -> list[Span]:
        raise NlpError

    async def lemma_candidates(
        self, _sentence: str, _char_start: int, _char_end: int
    ) -> list[LemmaCandidate]:
        raise NlpError


def test_text_is_located_inside_its_sentence_case_insensitively() -> None:
    assert locate("bank", "They sat on the Bank.") == ("They sat on the Bank.", 16)


def test_text_missing_from_the_sentence_is_analysed_alone() -> None:
    assert locate("bank", "Something else entirely.") == ("bank", 0)
    assert locate("bank", None) == ("bank", 0)


async def test_lemma_comes_first_then_the_normalised_text() -> None:
    analyzer = FakeTextAnalyzer({"went": ("go", UniversalPos.VERB)})

    target = await build_target(analyzer, "  Went ", "He went home.")

    assert target.candidates == ("go", "went")
    assert target.text == "went"
    assert target.part_of_speech == PartOfSpeech.VERB
    assert target.sentence == "He went home."
    assert target.lexeme_type == LexemeType.WORD


async def test_identical_lemma_is_not_repeated() -> None:
    target = await build_target(FakeTextAnalyzer(), "Bank", None)

    assert target.candidates == ("bank",)
    assert target.sentence is None
    assert target.part_of_speech == PartOfSpeech.NOUN


async def test_phrase_is_marked_as_a_phrase() -> None:
    target = await build_target(FakeTextAnalyzer(), "look forward to", None)

    assert target.lexeme_type == LexemeType.PHRASE


async def test_analyser_failure_falls_back_to_the_text_itself() -> None:
    target = await build_target(BrokenAnalyzer(), "Went", "He went home.")

    assert target.candidates == ("went",)
    assert target.part_of_speech is None


async def test_blank_context_is_ignored() -> None:
    target = await build_target(FakeTextAnalyzer(), "bank", "   ")

    assert target.sentence is None


def test_text_inside_another_word_is_not_a_match() -> None:
    assert locate("art", "He is smart, an art lover.") == ("He is smart, an art lover.", 16)
