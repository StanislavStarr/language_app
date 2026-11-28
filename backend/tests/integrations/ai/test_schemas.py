from typing import get_args

import pytest
from app.integrations.ai.schemas.fallback_meanings import (
    MAX_FALLBACK_MEANINGS,
    FallbackMeaning,
    FallbackMeaningsOutput,
    PartOfSpeechName,
    check_fallback_meanings,
)
from app.integrations.ai.schemas.meaning_content import MeaningContentOutput, check_meaning_content
from app.integrations.ai.schemas.russian import is_short_russian_text
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput, check_sense_selection
from app.integrations.ai.schemas.translations import (
    MAX_TRANSLATIONS_PER_MEANING,
    TranslatedMeaning,
    TranslationsOutput,
    check_translations,
)
from app.integrations.ai.schemas.words import contains_any
from app.modules.lexicon.enums import PartOfSpeech
from openai.lib._pydantic import to_strict_json_schema

CANDIDATES = frozenset({10, 11})
BANK_FORMS = ("bank", "banks", "banked", "banking")
ALLOWED_SCHEMA_KEYWORDS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "anyOf",
    "enum",
    "$ref",
    "$defs",
    "title",
}


def selection(**fields: object) -> SenseSelectionOutput:
    values: dict[str, object] = {
        "selected_meaning_id": 10,
        "contextual_translation": "банк",
        "confidence": 0.9,
    }
    return SenseSelectionOutput.model_validate({**values, **fields})


def schema_keywords(node: object) -> set[str]:
    if isinstance(node, list):
        return set().union(*(schema_keywords(item) for item in node))
    if not isinstance(node, dict):
        return set()
    keywords: set[str] = set()
    for key, value in node.items():
        if key in {"properties", "$defs"} and isinstance(value, dict):
            keywords.add(key)
            keywords.update(*(schema_keywords(child) for child in value.values()))
        else:
            keywords.add(key)
            keywords.update(schema_keywords(value))
    return keywords


@pytest.mark.parametrize(
    "model",
    [SenseSelectionOutput, MeaningContentOutput, TranslationsOutput, FallbackMeaningsOutput],
)
def test_schemas_sent_to_the_model_use_only_basic_keywords(model: type) -> None:
    schema = to_strict_json_schema(model)

    assert schema_keywords(schema) <= ALLOWED_SCHEMA_KEYWORDS


class TestSenseSelection:
    def test_valid_choice(self) -> None:
        check_sense_selection(selection(), CANDIDATES)

    def test_no_fitting_meaning_is_allowed(self) -> None:
        check_sense_selection(
            selection(selected_meaning_id=None, contextual_translation=None, confidence=0.2),
            CANDIDATES,
        )

    def test_unknown_meaning_id_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="candidates"):
            check_sense_selection(selection(selected_meaning_id=99), CANDIDATES)

    def test_translation_without_a_choice_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="null"):
            check_sense_selection(selection(selected_meaning_id=None), CANDIDATES)

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_confidence_must_be_a_probability(self, confidence: float) -> None:
        with pytest.raises(ValueError, match="confidence"):
            check_sense_selection(selection(confidence=confidence), CANDIDATES)

    @pytest.mark.parametrize("translation", ["bank", "", "   ", "банк (учреждение)", "я" * 81])
    def test_contextual_translation_must_be_short_russian_text(self, translation: str) -> None:
        with pytest.raises(ValueError, match="Russian"):
            check_sense_selection(selection(contextual_translation=translation), CANDIDATES)


class TestMeaningContent:
    def output(self, definition: str, example: str) -> MeaningContentOutput:
        return MeaningContentOutput(definition=definition, example=example)

    def test_good_content(self) -> None:
        check_meaning_content(
            self.output("A place where people keep money.", "She works at the bank near here."),
            BANK_FORMS,
        )

    def test_example_may_use_an_inflected_form(self) -> None:
        check_meaning_content(
            self.output("A place where people keep money.", "Two banks opened on our street."),
            BANK_FORMS,
        )

    @pytest.mark.parametrize("definition", ["The bank where money is kept.", "Places like BANKS."])
    def test_definition_must_not_contain_the_word_or_its_forms(self, definition: str) -> None:
        with pytest.raises(ValueError, match="definition"):
            check_meaning_content(self.output(definition, "She works at the bank."), BANK_FORMS)

    def test_a_longer_word_does_not_count_as_the_target(self) -> None:
        with pytest.raises(ValueError, match="example"):
            check_meaning_content(
                self.output("Someone who works with money.", "The banker called me."), ("bank",)
            )

    def test_example_must_contain_the_word(self) -> None:
        with pytest.raises(ValueError, match="example"):
            check_meaning_content(
                self.output("A place where people keep money.", "I like walking in the park."),
                BANK_FORMS,
            )

    @pytest.mark.parametrize(
        ("definition", "example"),
        [("short", "She works at the bank."), ("A" * 201, "She works at the bank.")],
    )
    def test_lengths_are_limited(self, definition: str, example: str) -> None:
        with pytest.raises(ValueError, match="definition"):
            check_meaning_content(self.output(definition, example), BANK_FORMS)

    def test_example_length_is_limited(self) -> None:
        with pytest.raises(ValueError, match="example"):
            check_meaning_content(
                self.output("A place where people keep money.", "bank " * 50), BANK_FORMS
            )

    def test_a_phrase_target_is_matched_as_a_whole(self) -> None:
        check_meaning_content(
            self.output("To feel excited about something coming.", "We look forward to the trip."),
            ("look forward to", "looks forward to"),
        )


class TestTranslations:
    def output(self, *items: tuple[int, list[str]]) -> TranslationsOutput:
        return TranslationsOutput(
            items=[TranslatedMeaning(meaning_id=i, translations=t) for i, t in items]
        )

    def test_good_translations(self) -> None:
        check_translations(
            self.output((10, ["банк", "касса"]), (11, ["ссуда"])), frozenset({10, 11})
        )

    @pytest.mark.parametrize(
        "items",
        [
            [(10, ["банк"])],
            [(10, ["банк"]), (11, ["касса"]), (12, ["вал"])],
            [(10, ["банк"]), (10, ["касса"])],
        ],
    )
    def test_every_requested_meaning_must_appear_exactly_once(
        self, items: list[tuple[int, list[str]]]
    ) -> None:
        with pytest.raises(ValueError, match="exactly once"):
            check_translations(self.output(*items), frozenset({10, 11}))

    @pytest.mark.parametrize(
        "translation", ["bank", "  ", "я" * 61, "bank банк", "банк (учреждение)", "банк [1]"]
    )
    def test_translation_must_be_short_russian_text(self, translation: str) -> None:
        with pytest.raises(ValueError, match="Russian"):
            check_translations(self.output((10, [translation])), frozenset({10}))

    def test_translations_of_one_meaning_must_not_repeat(self) -> None:
        with pytest.raises(ValueError, match="repeat"):
            check_translations(self.output((10, ["банк", "Банк "])), frozenset({10}))

    def test_number_of_translations_is_limited(self) -> None:
        too_many = ["банк", "касса", "ссуда", "вал"][: MAX_TRANSLATIONS_PER_MEANING + 1]

        with pytest.raises(ValueError, match="translations"):
            check_translations(self.output((10, too_many)), frozenset({10}))
        with pytest.raises(ValueError, match="translations"):
            check_translations(self.output((10, [])), frozenset({10}))


class TestFallbackMeanings:
    def meaning(self, gloss: str = "A thing that people use.") -> FallbackMeaning:
        return FallbackMeaning(part_of_speech="noun", gloss=gloss)

    def test_found_with_meanings(self) -> None:
        output = FallbackMeaningsOutput(found=True, meanings=[self.meaning()])

        check_fallback_meanings(output, "gadget")

    def test_not_found_with_no_meanings(self) -> None:
        check_fallback_meanings(FallbackMeaningsOutput(found=False, meanings=[]), "gadget")

    @pytest.mark.parametrize(
        ("found", "meanings"),
        [(True, []), (False, [FallbackMeaning(part_of_speech="noun", gloss="Some thing.")])],
    )
    def test_found_flag_must_match_the_meanings(
        self, found: bool, meanings: list[FallbackMeaning]
    ) -> None:
        with pytest.raises(ValueError, match="found"):
            check_fallback_meanings(FallbackMeaningsOutput(found=found, meanings=meanings), "x")

    def test_number_of_meanings_is_limited(self) -> None:
        output = FallbackMeaningsOutput(
            found=True, meanings=[self.meaning()] * (MAX_FALLBACK_MEANINGS + 1)
        )

        with pytest.raises(ValueError, match="at most"):
            check_fallback_meanings(output, "gadget")

    @pytest.mark.parametrize("gloss", ["Tiny", "x" * 201])
    def test_gloss_length_is_limited(self, gloss: str) -> None:
        output = FallbackMeaningsOutput(found=True, meanings=[self.meaning(gloss)])

        with pytest.raises(ValueError, match="characters"):
            check_fallback_meanings(output, "gadget")

    def test_gloss_must_not_contain_the_target_word(self) -> None:
        output = FallbackMeaningsOutput(found=True, meanings=[self.meaning("A gadget for work.")])

        with pytest.raises(ValueError, match="target word"):
            check_fallback_meanings(output, "gadget")

    def test_part_of_speech_is_one_of_the_lexicon_values(self) -> None:
        assert set(get_args(PartOfSpeechName.__value__)) == {pos.value for pos in PartOfSpeech}
        with pytest.raises(ValueError, match="part_of_speech"):
            FallbackMeaning.model_validate({"part_of_speech": "gizmo", "gloss": "A thing."})


@pytest.mark.parametrize(
    ("text", "words", "expected"),
    [
        ("The Bank opened.", ["bank"], True),
        ("Banks are open.", ["bank"], False),
        ("Banks are open.", ["bank", "banks"], True),
        ("a-bank-b", ["bank"], True),
        ("a café here", ["caf"], False),
        ("a café here", ["café"], True),
        ("anything", [], False),
        ("anything", [" "], False),
    ],
)
def test_word_matching_uses_whole_words(text: str, words: list[str], expected: bool) -> None:
    assert contains_any(text, words) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("банк", True),
        ("класть в банк", True),
        ("", False),
        ("bank", False),
        ("банк bank", False),
        ("банк (учреждение)", False),
        ("123", False),
    ],
)
def test_short_russian_text_rule(text: str, expected: bool) -> None:
    assert is_short_russian_text(text, 60) is expected
