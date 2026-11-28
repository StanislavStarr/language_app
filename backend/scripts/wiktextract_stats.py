from collections import defaultdict
from dataclasses import dataclass, field

from scripts.wiktextract import (
    MAX_MEANINGS_PER_POS,
    NAME_POS,
    PLAIN_WORD,
    US_IPA_TAGS,
    Entry,
    PhraseKind,
    is_form_sense,
    label_matches_gloss,
    lemma_senses,
    phrase_kind,
    phrase_max_rank,
    russian_translations,
    usable_forms,
)


@dataclass(frozen=True, slots=True)
class MeaningRecord:
    pos: str
    gloss_bytes: int
    has_russian: bool


@dataclass(slots=True)
class WordAggregate:
    lemma_entries: int = 0
    form_entries: int = 0
    has_ipa: bool = False
    has_us_ipa: bool = False
    has_mp3: bool = False
    meanings: list[MeaningRecord] = field(default_factory=list)
    russian: set[tuple[str, str]] = field(default_factory=set)
    russian_labels: int = 0
    russian_labels_linked: int = 0
    forms: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class PhraseRecord:
    word: str
    kind: PhraseKind
    max_rank: int | None
    has_russian: bool
    gloss_bytes: int
    russian_bytes: int


@dataclass(slots=True)
class Collected:
    ranks: dict[str, int]
    words: dict[str, WordAggregate] = field(default_factory=dict)
    form_targets: dict[str, set[str]] = field(default_factory=dict)
    phrases: list[PhraseRecord] = field(default_factory=list)
    entries: int = 0
    invalid_entries: int = 0
    other_language_entries: int = 0
    name_entries: int = 0


def meaning_records(entry: Entry) -> tuple[list[MeaningRecord], int, int]:
    translations = russian_translations(entry)
    labels = {item.sense for item in translations if item.sense}
    linked_labels: set[str] = set()
    records: list[MeaningRecord] = []
    for sense in lemma_senses(entry):
        gloss = sense.glosses[-1]
        matched = {label for label in labels if label_matches_gloss(label, gloss)}
        linked_labels |= matched
        records.append(MeaningRecord(entry.pos, len(gloss.encode()), bool(matched)))
    return records, len(labels), len(linked_labels)


def add_phrase(collected: Collected, entry: Entry) -> None:
    translations = russian_translations(entry)
    glosses = [sense.glosses[-1] for sense in lemma_senses(entry)]
    collected.phrases.append(
        PhraseRecord(
            word=entry.word.lower(),
            kind=phrase_kind(entry),
            max_rank=phrase_max_rank(entry.word, collected.ranks),
            has_russian=bool(translations),
            gloss_bytes=sum(len(gloss.encode()) for gloss in glosses),
            russian_bytes=sum(len(item.word.encode()) for item in translations),
        )
    )


def add_word(collected: Collected, entry: Entry, key: str) -> None:
    aggregate = collected.words.setdefault(key, WordAggregate())
    if not lemma_senses(entry):
        aggregate.form_entries += 1
        return
    aggregate.lemma_entries += 1
    aggregate.has_ipa |= any(sound.ipa for sound in entry.sounds)
    aggregate.has_us_ipa |= any(
        sound.ipa and not US_IPA_TAGS.isdisjoint(sound.tags) for sound in entry.sounds
    )
    aggregate.has_mp3 |= any(sound.mp3_url for sound in entry.sounds)
    records, label_count, linked_count = meaning_records(entry)
    aggregate.meanings.extend(records)
    aggregate.russian_labels += label_count
    aggregate.russian_labels_linked += linked_count
    aggregate.russian |= {(item.sense, item.word) for item in russian_translations(entry)}
    aggregate.forms |= usable_forms(entry)


def record_form_targets(collected: Collected, entry: Entry, key: str) -> None:
    is_inflection = bool(entry.senses) and all(is_form_sense(sense) for sense in entry.senses)
    if not is_inflection:
        return
    targets = {
        target.word.lower() for sense in entry.senses for target in sense.form_of if target.word
    }
    if targets:
        collected.form_targets.setdefault(key, set()).update(targets)


def collect_entry(collected: Collected, entry: Entry) -> None:
    collected.entries += 1
    if entry.lang_code != "en":
        collected.other_language_entries += 1
        return
    if entry.pos == NAME_POS:
        collected.name_entries += 1
        return
    key = entry.word.lower()
    if " " in entry.word.strip():
        add_phrase(collected, entry)
        return
    if key in collected.ranks and PLAIN_WORD.match(key):
        add_word(collected, entry, key)
        record_form_targets(collected, entry, key)


def capped_meanings(aggregate: WordAggregate) -> list[MeaningRecord]:
    per_pos: dict[str, int] = defaultdict(int)
    kept: list[MeaningRecord] = []
    for record in aggregate.meanings:
        if per_pos[record.pos] < MAX_MEANINGS_PER_POS:
            per_pos[record.pos] += 1
            kept.append(record)
    return kept
