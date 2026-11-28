import pytest
from app.modules.lexicon.enums import PartOfSpeech
from app.modules.lexicon.part_of_speech import UNIVERSAL_TO_PART_OF_SPEECH, to_part_of_speech


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("noun", PartOfSpeech.NOUN),
        ("Verb", PartOfSpeech.VERB),
        ("adjective", PartOfSpeech.ADJECTIVE),
        ("adj", PartOfSpeech.ADJECTIVE),
        ("exclamation", PartOfSpeech.INTERJECTION),
        ("article", PartOfSpeech.DETERMINER),
        ("proverb", PartOfSpeech.PHRASE),
        ("symbol", PartOfSpeech.OTHER),
        ("", PartOfSpeech.OTHER),
    ],
)
def test_names_of_both_dictionaries_map_to_one_enum(name: str, expected: PartOfSpeech) -> None:
    assert to_part_of_speech(name) == expected


def test_every_universal_tag_used_by_the_lookup_has_a_target() -> None:
    assert UNIVERSAL_TO_PART_OF_SPEECH["AUX"] == PartOfSpeech.VERB
    assert UNIVERSAL_TO_PART_OF_SPEECH["PROPN"] == PartOfSpeech.NOUN
