from dataclasses import asdict, dataclass

from scripts.wiktextract import PLAIN_WORD
from scripts.wiktextract_stats import Collected, PhraseRecord, capped_meanings

ROW_OVERHEAD_BYTES = 48
BTREE_ENTRY_OVERHEAD_BYTES = 16
TRIGRAM_INDEX_FACTOR = 3
LEXEME_FIXED_BYTES = 90
FORM_FIXED_BYTES = 24
MEANING_FIXED_BYTES = 40
TRANSLATION_FIXED_BYTES = 24
BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class TableSizes:
    lexeme: int
    lexeme_form: int
    meaning: int
    translation: int

    @property
    def total_mb(self) -> float:
        return (self.lexeme + self.lexeme_form + self.meaning + self.translation) / BYTES_PER_MB


@dataclass(frozen=True, slots=True)
class CoverageRow:
    top_n: int
    plain_word_share: float
    found_any_share: float
    found_lemma_share: float
    form_only_resolved_share: float
    ipa_share: float
    us_ipa_share: float
    mp3_share: float
    avg_meanings_capped: float
    avg_meanings_uncapped: float
    lemmas_with_russian_share: float
    meanings_with_russian_share: float
    russian_labels_linked_share: float
    russian_items_without_label_share: float
    text_token_coverage: float
    found_token_share: float
    lemmas_with_forms_share: float
    avg_forms: float
    lexeme_rows: int
    form_rows: int
    meaning_rows: int
    translation_rows: int
    sizes: TableSizes


@dataclass(frozen=True, slots=True)
class PhraseRow:
    kind: str
    total: int
    with_russian: int
    distinct: int
    within_top_n: dict[int, int]


def share(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def share_float(part: float, whole: float) -> float:
    return part / whole if whole else 0.0


def table_sizes(
    lexeme_texts: list[int],
    form_texts: list[int],
    gloss_bytes: list[int],
    translation_texts: list[int],
) -> TableSizes:
    lexeme = sum(
        ROW_OVERHEAD_BYTES
        + LEXEME_FIXED_BYTES
        + 2 * size
        + (size + BTREE_ENTRY_OVERHEAD_BYTES)
        + TRIGRAM_INDEX_FACTOR * size
        for size in lexeme_texts
    )
    form = sum(
        ROW_OVERHEAD_BYTES + FORM_FIXED_BYTES + size + 2 * (size + BTREE_ENTRY_OVERHEAD_BYTES)
        for size in form_texts
    )
    meaning = sum(
        ROW_OVERHEAD_BYTES + MEANING_FIXED_BYTES + size + BTREE_ENTRY_OVERHEAD_BYTES
        for size in gloss_bytes
    )
    translation = sum(
        ROW_OVERHEAD_BYTES + TRANSLATION_FIXED_BYTES + size + (size + BTREE_ENTRY_OVERHEAD_BYTES)
        for size in translation_texts
    )
    return TableSizes(lexeme, form, meaning, translation)


def coverage_row(collected: Collected, top_n: int, frequencies: dict[str, float]) -> CoverageRow:
    in_top = [word for word, rank in collected.ranks.items() if rank <= top_n]
    selected = [word for word in in_top if PLAIN_WORD.match(word)]
    aggregates = {word: collected.words[word] for word in selected if word in collected.words}
    lemmas = {word: item for word, item in aggregates.items() if item.lemma_entries}
    form_only = [word for word, item in aggregates.items() if not item.lemma_entries]
    resolved = [
        word for word in form_only if collected.form_targets.get(word, set()) & lemmas.keys()
    ]
    found = set(lemmas) | set(resolved)
    capped = {word: capped_meanings(item) for word, item in lemmas.items()}
    meaning_rows = sum(len(records) for records in capped.values())
    all_forms = {form for item in lemmas.values() for form in item.forms}
    labels = sum(item.russian_labels for item in lemmas.values())
    linked_labels = sum(item.russian_labels_linked for item in lemmas.values())
    total_russian = sum(len(item.russian) for item in lemmas.values())
    unlabeled = sum(1 for item in lemmas.values() for sense, _ in item.russian if not sense)
    translation_bytes = [len(text.encode()) for item in lemmas.values() for _, text in item.russian]
    sizes = table_sizes(
        [len(word) for word in lemmas],
        [len(form.encode()) for form in all_forms],
        [record.gloss_bytes for records in capped.values() for record in records],
        translation_bytes,
    )
    text_mass = sum(frequencies.get(word, 0.0) for word in in_top)
    return CoverageRow(
        top_n=top_n,
        plain_word_share=share(len(selected), len(in_top)),
        found_any_share=share(len(aggregates), len(selected)),
        found_lemma_share=share(len(lemmas), len(selected)),
        form_only_resolved_share=share(len(resolved), len(selected)),
        ipa_share=share(sum(item.has_ipa for item in lemmas.values()), len(lemmas)),
        us_ipa_share=share(sum(item.has_us_ipa for item in lemmas.values()), len(lemmas)),
        mp3_share=share(sum(item.has_mp3 for item in lemmas.values()), len(lemmas)),
        avg_meanings_capped=share(meaning_rows, len(lemmas)),
        avg_meanings_uncapped=share(
            sum(len(item.meanings) for item in lemmas.values()), len(lemmas)
        ),
        lemmas_with_russian_share=share(
            sum(bool(item.russian) for item in lemmas.values()), len(lemmas)
        ),
        meanings_with_russian_share=share(
            sum(record.has_russian for records in capped.values() for record in records),
            meaning_rows,
        ),
        russian_labels_linked_share=share(linked_labels, labels),
        russian_items_without_label_share=share(unlabeled, total_russian),
        text_token_coverage=text_mass,
        found_token_share=share_float(sum(frequencies.get(word, 0.0) for word in found), text_mass),
        lemmas_with_forms_share=share(
            sum(bool(item.forms) for item in lemmas.values()), len(lemmas)
        ),
        avg_forms=share(sum(len(item.forms) for item in lemmas.values()), len(lemmas)),
        lexeme_rows=len(lemmas),
        form_rows=len(all_forms),
        meaning_rows=meaning_rows,
        translation_rows=len(translation_bytes),
        sizes=sizes,
    )


def phrase_rows(phrases: list[PhraseRecord], top_ns: tuple[int, ...]) -> list[PhraseRow]:
    rows: list[PhraseRow] = []
    for kind in ("phrasal_verb", "idiom", "phrase", "other"):
        of_kind = [item for item in phrases if item.kind == kind]
        rows.append(
            PhraseRow(
                kind=kind,
                total=len(of_kind),
                with_russian=sum(item.has_russian for item in of_kind),
                distinct=len({item.word for item in of_kind}),
                within_top_n={
                    top_n: len(
                        {
                            item.word
                            for item in of_kind
                            if item.max_rank is not None and item.max_rank <= top_n
                        }
                    )
                    for top_n in top_ns
                },
            )
        )
    return rows


def phrase_import_size(phrases: list[PhraseRecord], top_n: int) -> tuple[int, TableSizes]:
    chosen = [
        item
        for item in phrases
        if item.kind != "other" and item.max_rank is not None and item.max_rank <= top_n
    ]
    words = {item.word for item in chosen}
    sizes = table_sizes(
        [len(word) for word in words],
        [],
        [item.gloss_bytes for item in chosen],
        [item.russian_bytes for item in chosen if item.has_russian],
    )
    return len(words), sizes


def summarize(
    collected: Collected, top_ns: tuple[int, ...], frequencies: dict[str, float]
) -> dict[str, object]:
    phrase_count, phrase_sizes = phrase_import_size(collected.phrases, min(top_ns))
    return {
        "entries": collected.entries,
        "invalid_entries": collected.invalid_entries,
        "other_language_entries": collected.other_language_entries,
        "name_entries": collected.name_entries,
        "coverage": [asdict(coverage_row(collected, top_n, frequencies)) for top_n in top_ns],
        "phrases": [asdict(row) for row in phrase_rows(collected.phrases, top_ns)],
        "phrase_import": {
            "top_n": min(top_ns),
            "distinct_phrases": phrase_count,
            "size_mb": phrase_sizes.total_mb,
        },
    }
