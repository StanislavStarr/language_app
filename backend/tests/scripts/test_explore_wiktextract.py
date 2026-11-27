import gzip
import json
from pathlib import Path

import pytest
from scripts.explore_wiktextract import build_ranks, explore
from scripts.wiktextract_stats import (
    PLAIN_WORD,
    Collected,
    Entry,
    capped_meanings,
    label_matches_gloss,
    phrase_kind,
)
from scripts.wiktextract_summary import coverage_row, phrase_rows

TOP_N = 30_000
FREQUENCIES = {"go": 0.01, "went": 0.002, "bank": 0.001, "house": 0.001}


def entry(word: str, pos: str, **fields: object) -> str:
    return json.dumps({"word": word, "lang_code": "en", "pos": pos, **fields})


def senses(*glosses: str, **extra: object) -> list[dict[str, object]]:
    return [{"glosses": [gloss], **extra} for gloss in glosses]


@pytest.fixture
def collected(tmp_path: Path) -> Collected:
    lines = [
        entry(
            "go",
            "verb",
            senses=senses("To move through space.", "To leave a place."),
            forms=[
                {"form": "went", "tags": ["past"]},
                {"form": "going", "tags": ["present", "participle"]},
                {"form": "no-table-tags", "tags": ["table-tags"]},
            ],
            sounds=[
                {"ipa": "/goʊ/", "tags": ["General-American"]},
                {"mp3_url": "https://upload.wikimedia.org/go.mp3"},
            ],
            translations=[
                {"lang_code": "ru", "word": "идти", "sense": "move through space"},
                {"lang_code": "ru", "word": "уходить", "sense": "unrelated label"},
                {"lang_code": "de", "word": "gehen", "sense": "move through space"},
            ],
        ),
        entry(
            "went",
            "verb",
            senses=[
                {"glosses": ["simple past of go"], "form_of": [{"word": "go"}], "tags": ["form-of"]}
            ],
        ),
        entry("bank", "noun", senses=senses("An institution for money.")),
        entry("will", "noun", senses=senses("A legal document.")),
        entry("Will", "name", senses=senses("A male given name.")),
        entry("don't", "verb", senses=senses("Do not.")),
        entry("café", "noun", senses=senses("A coffee shop.")),
        entry(
            "gone",
            "verb",
            senses=[{"glosses": ["past participle of go"], "form_of": [{"word": "goer"}]}],
        ),
        entry("house", "noun", senses=senses(*[f"Other meaning {index}." for index in range(5)])),
        entry("make up", "verb", senses=senses("To invent.")),
        entry("by and large", "adv", senses=senses("Mostly.")),
        entry(
            "a stitch in time saves nine",
            "phrase",
            senses=senses("Prompt action prevents trouble."),
        ),
        entry("house", "noun", senses=senses(*[f"Meaning number {index}." for index in range(10)])),
        entry(
            "look forward to",
            "verb",
            senses=senses("To anticipate.", tags=["idiomatic"]),
            translations=[{"lang_code": "ru", "word": "ждать", "sense": "anticipate"}],
        ),
        entry("give up", "verb", senses=senses("To stop trying.")),
        json.dumps({"word": "chien", "lang_code": "fr", "pos": "noun", "senses": []}),
        '{"lang_code": "en", not json',
        json.dumps({"pos": "noun", "lang_code": "en"}),
    ]
    path = tmp_path / "sample.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return explore(path)


def test_counts_entries_invalid_lines_and_other_languages(collected: Collected) -> None:
    assert collected.entries == 16
    assert collected.invalid_entries == 2
    assert collected.other_language_entries == 1


def test_lemma_gets_ipa_mp3_forms_and_filters_junk_forms(collected: Collected) -> None:
    aggregate = collected.words["go"]

    assert aggregate.has_ipa
    assert aggregate.has_us_ipa
    assert aggregate.has_mp3
    assert aggregate.forms == {"went", "going"}


def test_only_russian_translations_are_kept_and_linked_by_label(collected: Collected) -> None:
    aggregate = collected.words["go"]

    assert aggregate.russian == {
        ("move through space", "идти"),
        ("unrelated label", "уходить"),
    }
    assert aggregate.russian_labels == 2
    assert aggregate.russian_labels_linked == 1
    assert [record.has_russian for record in aggregate.meanings] == [True, False]


def test_inflected_form_records_its_lemma_target(collected: Collected) -> None:
    assert collected.words["went"].lemma_entries == 0
    assert collected.form_targets["went"] == {"go"}


def test_coverage_row_shares_over_found_lemmas(collected: Collected) -> None:
    row = coverage_row(collected, TOP_N, FREQUENCIES)

    assert row.lexeme_rows == 4
    assert row.ipa_share == pytest.approx(1 / 4)
    assert row.mp3_share == pytest.approx(1 / 4)
    assert row.lemmas_with_russian_share == pytest.approx(1 / 4)
    assert row.russian_labels_linked_share == pytest.approx(0.5)
    assert row.form_rows == 2
    assert row.translation_rows == 2
    assert row.sizes.total_mb > 0


def test_phrases_are_classified_and_counted(collected: Collected) -> None:
    rows = {row.kind: row for row in phrase_rows(collected.phrases, (TOP_N,))}

    assert rows["idiom"].total == 1
    assert rows["idiom"].with_russian == 1
    assert rows["idiom"].within_top_n[TOP_N] == 1
    assert rows["phrasal_verb"].total == 2
    assert rows["phrase"].total == 1
    assert rows["other"].total == 1


def test_phrase_with_unknown_word_is_outside_every_top_n(tmp_path: Path) -> None:
    path = tmp_path / "phrase.jsonl"
    path.write_text(entry("zzyzx up", "verb", senses=senses("Nonsense.")) + "\n")

    rows = {row.kind: row for row in phrase_rows(explore(path).phrases, (TOP_N,))}

    assert rows["phrasal_verb"].total == 1
    assert rows["phrasal_verb"].within_top_n[TOP_N] == 0


@pytest.mark.parametrize(
    ("label", "gloss", "expected"),
    [
        ("institution", "An institution where one can place money.", True),
        ("branch office", "A branch office of a bank.", True),
        ("controller of a card game", "An institution for money.", False),
        ("", "Anything.", False),
        ("to go", "To go somewhere.", False),
    ],
)
def test_label_matching_requires_all_content_words(label: str, gloss: str, expected: bool) -> None:
    assert label_matches_gloss(label, gloss) is expected


def test_phrase_kind_prefers_phrasal_verb_over_idiom() -> None:
    parsed = Entry.model_validate_json(
        entry("give up", "verb", senses=senses("To stop.", tags=["idiomatic"]))
    )

    assert phrase_kind(parsed) == "phrasal_verb"


def test_reads_gzipped_raw_dump_and_skips_other_languages(tmp_path: Path) -> None:
    lines = [
        entry("bank", "noun", senses=senses("An institution for money.")),
        json.dumps({"word": "banque", "lang_code": "fr", "pos": "noun", "senses": []}),
    ]
    path = tmp_path / "raw.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as target:
        target.write("\n".join(lines) + "\n")

    collected = explore(path)

    assert collected.entries == 2
    assert collected.other_language_entries == 1
    assert "bank" in collected.words


def test_proper_names_never_count_as_the_common_word(collected: Collected) -> None:
    assert collected.name_entries == 1
    assert [record.pos for record in collected.words["will"].meanings] == ["noun"]


def test_only_plain_a_to_z_words_are_collected(collected: Collected) -> None:
    assert "don't" not in collected.words
    assert "café" not in collected.words


def test_meaning_cap_applies_across_entries_of_the_same_part_of_speech(
    collected: Collected,
) -> None:
    assert len(collected.words["house"].meanings) == 15
    assert len(capped_meanings(collected.words["house"])) == 8


def test_form_is_not_resolved_when_its_lemma_was_not_found(collected: Collected) -> None:
    row = coverage_row(collected, TOP_N, FREQUENCIES)

    assert collected.form_targets["gone"] == {"goer"}
    assert collected.form_targets["went"] == {"go"}
    assert row.form_only_resolved_share == pytest.approx(1 / row_selected_size())


def test_unlabeled_russian_translations_are_reported(tmp_path: Path) -> None:
    path = tmp_path / "unlabeled.jsonl"
    path.write_text(
        entry(
            "bank",
            "noun",
            senses=senses("An institution for money."),
            translations=[
                {"lang_code": "ru", "word": "банк", "sense": ""},
                {"lang_code": "ru", "word": "идти", "sense": "institution"},
            ],
        )
        + "\n"
    )

    row = coverage_row(explore(path), TOP_N, FREQUENCIES)

    assert row.russian_items_without_label_share == pytest.approx(0.5)


def test_max_lines_limits_the_read(tmp_path: Path) -> None:
    path = tmp_path / "many.jsonl"
    path.write_text(
        "\n".join(
            entry(word, "noun", senses=senses("A thing.")) for word in ("bank", "house", "go")
        )
        + "\n"
    )

    assert explore(path, max_lines=2).entries == 2


def row_selected_size() -> int:
    return len(
        [
            word
            for word, rank in build_ranks(TOP_N).items()
            if rank <= TOP_N and PLAIN_WORD.match(word)
        ]
    )
