import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RUSSIAN = "ru"
MAX_MEANINGS_PER_POS = 8
MIN_LABEL_TOKEN_LENGTH = 3
JUNK_FORM_TAGS = frozenset({"table-tags", "inflection-template", "class"})
JUNK_FORMS = frozenset({"no-table-tags"})
PARTICLES = frozenset(
    {"up", "down", "out", "off", "on", "in", "over", "away", "back", "around", "through", "along"}
)
PHRASE_POS = frozenset({"phrase", "proverb", "prep_phrase", "adv_phrase", "intj", "contraction"})
US_IPA_TAGS = frozenset({"US", "General-American"})
TOKEN_PATTERN = re.compile(r"[a-z0-9']+")
PLAIN_WORD = re.compile(r"^[a-z]+$")
NAME_POS = "name"

type PhraseKind = Literal["phrasal_verb", "idiom", "phrase", "other"]


class WiktextractModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class FormOf(WiktextractModel):
    word: str = ""


class Sense(WiktextractModel):
    glosses: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    form_of: list[FormOf] = Field(default_factory=list)


class Form(WiktextractModel):
    form: str = ""
    tags: list[str] = Field(default_factory=list)


class Sound(WiktextractModel):
    ipa: str | None = None
    mp3_url: str | None = None
    tags: list[str] = Field(default_factory=list)


class Translation(WiktextractModel):
    lang_code: str = ""
    word: str = ""
    sense: str = ""


class Entry(WiktextractModel):
    word: str
    lang_code: str = ""
    pos: str = ""
    senses: list[Sense] = Field(default_factory=list)
    forms: list[Form] = Field(default_factory=list)
    sounds: list[Sound] = Field(default_factory=list)
    translations: list[Translation] = Field(default_factory=list)


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


def tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def is_form_sense(sense: Sense) -> bool:
    return bool(sense.form_of) or "form-of" in sense.tags


def label_matches_gloss(label: str, gloss: str) -> bool:
    label_tokens = {token for token in tokens(label) if len(token) >= MIN_LABEL_TOKEN_LENGTH}
    if not label_tokens:
        return False
    return label_tokens <= set(tokens(gloss))


def russian_translations(entry: Entry) -> list[Translation]:
    return [item for item in entry.translations if item.lang_code == RUSSIAN and item.word]


def lemma_senses(entry: Entry) -> list[Sense]:
    return [sense for sense in entry.senses if sense.glosses and not is_form_sense(sense)]


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


def phrase_kind(entry: Entry) -> PhraseKind:
    parts = entry.word.lower().split()
    is_idiomatic = any("idiomatic" in sense.tags for sense in entry.senses)
    if entry.pos == "verb" and parts[-1] in PARTICLES:
        return "phrasal_verb"
    if is_idiomatic:
        return "idiom"
    if entry.pos in PHRASE_POS:
        return "phrase"
    return "other"


def phrase_max_rank(word: str, ranks: dict[str, int]) -> int | None:
    token_ranks = [ranks.get(token) for token in tokens(word)]
    if not token_ranks or any(rank is None for rank in token_ranks):
        return None
    return max(rank for rank in token_ranks if rank is not None)


def usable_forms(entry: Entry) -> set[str]:
    return {
        item.form.lower()
        for item in entry.forms
        if item.form
        and item.form not in JUNK_FORMS
        and JUNK_FORM_TAGS.isdisjoint(item.tags)
        and item.form.lower() != entry.word.lower()
    }


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
