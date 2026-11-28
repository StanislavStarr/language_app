import json

import pytest
from app.modules.lexicon.enums import LexemeType, PartOfSpeech
from app.modules.lexicon.part_of_speech import to_part_of_speech
from scripts.lexicon_collector import DraftCollector, collect_lexemes
from scripts.lexicon_drafts import (
    MAX_TRANSLATIONS_PER_MEANING,
    LexemeDraft,
    build_drafts,
    external_id,
)
from scripts.wiktextract import build_ranks

PHRASE_TOP_N = 30_000


def line(word: str, pos: str, **fields: object) -> str:
    return json.dumps({"word": word, "lang_code": "en", "pos": pos, **fields})


def senses(*glosses: str, **extra: object) -> list[dict[str, object]]:
    return [{"glosses": [gloss], **extra} for gloss in glosses]


def translations(*items: tuple[str, str], language: str = "ru") -> list[dict[str, str]]:
    return [{"lang_code": language, "sense": label, "word": word} for label, word in items]


def lines() -> list[str]:
    return [
        line(
            "GO",
            "noun",
            senses=senses("An abbreviation."),
            forms=[{"form": "GOs", "tags": ["plural"]}],
        ),
        line(
            "go",
            "verb",
            senses=senses("To move through space.", "To leave a place.", "To become."),
            forms=[
                {"form": "goes", "tags": ["third-person", "singular"]},
                {"form": "going", "tags": ["participle", "present"]},
                {"form": "no-table-tags", "tags": ["table-tags"]},
                {"form": "go", "tags": ["infinitive"]},
                {"form": "-", "tags": ["archaic"]},
            ],
            sounds=[
                {"ipa": "/ɡəʊ/", "tags": ["Received-Pronunciation"]},
                {"ipa": "/goʊ/", "tags": ["General-American"]},
                {"mp3_url": "https://upload.wikimedia.org/uk-go.mp3", "tags": ["UK"]},
                {"mp3_url": "https://upload.wikimedia.org/us-go.mp3", "tags": ["US"]},
            ],
            translations=[
                *translations(("move through space", "идти"), ("unrelated label", "ехать")),
                *translations(("move through space", "ходить"), language="ru")[:0],
                *translations(("move through space", "gehen"), language="de"),
            ],
        ),
        line(
            "went",
            "verb",
            senses=[
                {
                    "glosses": ["simple past of go"],
                    "form_of": [{"word": "go"}],
                    "tags": ["form-of", "past"],
                }
            ],
        ),
        line(
            "gone",
            "verb",
            senses=[
                {
                    "glosses": ["past participle of go"],
                    "form_of": [{"word": "go"}],
                    "tags": ["form-of", "participle", "past"],
                }
            ],
        ),
        line("bank", "noun", senses=senses(*[f"Noun meaning {number}." for number in range(10)])),
        line("bank", "noun", senses=senses("Noun meaning 1.", "A river bank.")),
        line("bank", "verb", senses=senses("To tilt.")),
        line("house", "noun", senses=senses("A building.")),
        line("will", "noun", senses=senses("A legal document.")),
        line("Will", "name", senses=senses("A given name.")),
        line("don't", "verb", senses=senses("Do not.")),
        line("café", "noun", senses=senses("A coffee shop.")),
        line("zzyzxqq", "noun", senses=senses("Not a frequent word.")),
        line(
            "look forward to",
            "verb",
            senses=senses("To anticipate.", tags=["idiomatic"]),
            forms=[{"form": "looks forward to", "tags": ["third-person"]}],
            translations=translations(("anticipate", "ждать")),
        ),
        line("give up", "verb", senses=senses("To stop trying.")),
        line("by and large", "adv", senses=senses("Mostly.")),
        json.dumps({"word": "chien", "lang_code": "fr", "pos": "noun", "senses": []}),
        '{"lang_code": "en", broken',
    ]


@pytest.fixture(scope="module")
def collector() -> DraftCollector:
    return collect_lexemes(lines(), build_ranks(60_000), PHRASE_TOP_N)


@pytest.fixture(scope="module")
def drafts(collector: DraftCollector) -> dict[str, LexemeDraft]:
    return {draft.normalized_text: draft for draft in build_drafts(collector)}


def test_only_frequent_plain_words_and_importable_phrases_become_lexemes(
    drafts: dict[str, LexemeDraft],
) -> None:
    assert set(drafts) == {"go", "bank", "house", "will", "look forward to", "give up"}


def test_invalid_lines_are_counted_and_other_languages_are_ignored(
    collector: DraftCollector,
) -> None:
    assert collector.invalid_lines == 1


def test_proper_names_are_not_merged_into_common_words(drafts: dict[str, LexemeDraft]) -> None:
    assert [meaning.gloss for meaning in drafts["will"].meanings] == ["A legal document."]


def test_meaning_gets_stable_order_and_external_id(drafts: dict[str, LexemeDraft]) -> None:
    go = drafts["go"]

    assert [meaning.sense_order for meaning in go.meanings] == [1, 2, 3]
    assert go.meanings[0].external_id == external_id(PartOfSpeech.VERB, "To move through space.")
    assert len({meaning.external_id for meaning in go.meanings}) == 3


def test_meanings_are_capped_per_part_of_speech_and_deduplicated(
    drafts: dict[str, LexemeDraft],
) -> None:
    bank = drafts["bank"]
    nouns = [meaning for meaning in bank.meanings if meaning.part_of_speech == PartOfSpeech.NOUN]
    verbs = [meaning for meaning in bank.meanings if meaning.part_of_speech == PartOfSpeech.VERB]

    assert len(nouns) == 8
    assert [meaning.gloss for meaning in nouns].count("Noun meaning 1.") == 1
    assert "A river bank." in [meaning.gloss for meaning in nouns]
    assert len(verbs) == 1
    assert [meaning.sense_order for meaning in bank.meanings] == list(range(1, 10))


def test_russian_translation_is_linked_by_label_and_unmatched_label_is_dropped(
    drafts: dict[str, LexemeDraft],
) -> None:
    go = drafts["go"]

    assert go.meanings[0].translations == ("идти",)
    assert go.meanings[1].translations == ()


def test_entries_spelled_exactly_like_the_key_win_over_capitalised_ones(
    drafts: dict[str, LexemeDraft],
) -> None:
    go = drafts["go"]

    assert go.text == "go"
    assert all(meaning.gloss != "An abbreviation." for meaning in go.meanings)
    assert "gos" not in {form.form_normalized for form in go.forms}


def test_a_label_with_partial_overlap_goes_to_the_closest_meaning() -> None:
    collector = collect_lexemes(
        [
            line(
                "bank",
                "noun",
                senses=senses("An institution for money.", "The land beside a river."),
                translations=translations(("edge of river", "ссуда")),
            )
        ],
        build_ranks(60_000),
        PHRASE_TOP_N,
    )

    (draft,) = list(build_drafts(collector))

    assert [meaning.translations for meaning in draft.meanings] == [(), ("ссуда",)]


def test_an_unmatched_label_is_attached_when_the_entry_has_a_single_sense() -> None:
    collector = collect_lexemes(
        [
            line(
                "house",
                "noun",
                senses=senses("A building."),
                translations=translations(("something else", "дом")),
            )
        ],
        build_ranks(60_000),
        PHRASE_TOP_N,
    )

    (draft,) = list(build_drafts(collector))

    assert draft.meanings[0].translations == ("дом",)


def test_only_russian_translations_are_kept(drafts: dict[str, LexemeDraft]) -> None:
    assert all("gehen" not in meaning.translations for meaning in drafts["go"].meanings)


def test_word_without_translation_keeps_its_meanings(drafts: dict[str, LexemeDraft]) -> None:
    house = drafts["house"]

    assert [meaning.translations for meaning in house.meanings] == [()]


def test_every_etymology_is_represented_and_keeps_its_own_translations() -> None:
    collector = collect_lexemes(
        [
            line(
                "bank",
                "noun",
                senses=senses(*[f"Money sense {number}." for number in range(10)]),
                translations=translations(("money sense", "банк")),
            ),
            line(
                "bank",
                "noun",
                senses=senses("The edge of a river.", "A slope of earth."),
                translations=translations(("edge of river", "идти")),
            ),
        ],
        build_ranks(60_000),
        PHRASE_TOP_N,
    )

    (draft,) = list(build_drafts(collector))
    by_gloss = {meaning.gloss: meaning for meaning in draft.meanings}

    assert len(draft.meanings) == 8
    assert by_gloss["The edge of a river."].translations == ("идти",)
    assert all(
        "идти" not in meaning.translations
        for meaning in draft.meanings
        if meaning.gloss.startswith("Money")
    )


def test_an_unmatched_label_is_dropped_when_other_senses_were_cut_by_the_cap() -> None:
    crowded = senses("A building.", *[f"Other meaning {number}." for number in range(9)])
    collector = collect_lexemes(
        [
            line("house", "noun", senses=senses("Seen already.")),
            line(
                "house",
                "noun",
                senses=crowded,
                translations=translations(("unrelated label", "дом")),
            ),
        ],
        build_ranks(60_000),
        PHRASE_TOP_N,
    )

    (draft,) = list(build_drafts(collector))

    assert all("дом" not in meaning.translations for meaning in draft.meanings)


def test_translations_per_meaning_are_limited() -> None:
    many = translations(*[("anticipate", f"перевод{number}") for number in range(9)])
    collector = collect_lexemes(
        [line("house", "noun", senses=senses("A building."), translations=many)],
        build_ranks(60_000),
        PHRASE_TOP_N,
    )

    (draft,) = list(build_drafts(collector))

    assert len(draft.meanings[0].translations) == MAX_TRANSLATIONS_PER_MEANING


def test_forms_come_from_the_lemma_and_from_inflected_entries(
    drafts: dict[str, LexemeDraft],
) -> None:
    forms = {form.form_normalized: form.tags for form in drafts["go"].forms}

    assert forms["goes"] == ("singular", "third-person")
    assert forms["going"] == ("participle", "present")
    assert forms["went"] == ("past",)
    assert forms["gone"] == ("participle", "past")
    assert "no-table-tags" not in forms
    assert "-" not in forms
    assert "go" not in forms


def test_pronunciation_prefers_us_variants(drafts: dict[str, LexemeDraft]) -> None:
    go = drafts["go"]

    assert go.ipa == "/goʊ/"
    assert go.audio_url == "https://upload.wikimedia.org/us-go.mp3"


def test_words_have_frequency_rank_and_phrases_do_not(drafts: dict[str, LexemeDraft]) -> None:
    assert drafts["go"].frequency_rank == build_ranks(60_000)["go"]
    assert drafts["go"].lexeme_type == LexemeType.WORD
    assert drafts["look forward to"].lexeme_type == LexemeType.PHRASE
    assert drafts["look forward to"].frequency_rank is None


def test_phrase_keeps_its_translation_and_forms(drafts: dict[str, LexemeDraft]) -> None:
    phrase = drafts["look forward to"]

    assert phrase.meanings[0].translations == ("ждать",)
    assert [form.form_normalized for form in phrase.forms] == ["looks forward to"]


def test_phrases_outside_the_frequency_limit_are_skipped() -> None:
    collector = collect_lexemes(
        [line("zzyzxqq up", "verb", senses=senses("Nonsense."))], build_ranks(60_000), PHRASE_TOP_N
    )

    assert list(build_drafts(collector)) == []


@pytest.mark.parametrize(
    ("pos", "expected"),
    [
        ("noun", PartOfSpeech.NOUN),
        ("adj", PartOfSpeech.ADJECTIVE),
        ("article", PartOfSpeech.DETERMINER),
        ("proverb", PartOfSpeech.PHRASE),
        ("symbol", PartOfSpeech.OTHER),
    ],
)
def test_part_of_speech_mapping(pos: str, expected: PartOfSpeech) -> None:
    assert to_part_of_speech(pos) == expected
