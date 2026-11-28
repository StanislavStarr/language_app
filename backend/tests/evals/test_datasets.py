from collections import Counter

from evals.dataset import ContentCase, SenseCase, read_jsonl


def test_sense_selection_dataset_is_consistent_and_covers_no_fit_cases() -> None:
    cases = read_jsonl("sense_selection", SenseCase)

    assert len(cases) == 40
    assert len({case.id for case in cases}) == 40
    assert sum(case.expected_id is None for case in cases) >= 8
    for case in cases:
        ids = [candidate.id for candidate in case.candidates]
        assert len(ids) == len(set(ids)) >= 2
        assert case.expected_id is None or case.expected_id in ids


def test_sense_selection_dataset_has_several_contexts_per_word() -> None:
    cases = read_jsonl("sense_selection", SenseCase)

    per_word = Counter(case.word for case in cases)

    assert len(per_word) >= 10
    assert min(per_word.values()) >= 2


def test_meaning_content_dataset_has_thirty_meanings_at_two_levels() -> None:
    cases = read_jsonl("meaning_content", ContentCase)

    assert len(cases) == 30
    assert len({case.id for case in cases}) == 30
    assert {tuple(case.levels) for case in cases} == {("A2", "B2")}
    assert all(case.gloss and case.part_of_speech for case in cases)


def test_limit_takes_the_first_cases() -> None:
    assert [c.id for c in read_jsonl("sense_selection", SenseCase, 3)] == [
        "bank-money",
        "bank-river",
        "bank-verb",
    ]
