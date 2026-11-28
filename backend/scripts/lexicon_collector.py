from collections.abc import Iterable
from dataclasses import dataclass, field

from app.integrations.nlp.normalization import normalize_text
from app.modules.lexicon.enums import LexemeType
from pydantic import ValidationError

from scripts.wiktextract import (
    ENGLISH_MARKER,
    NAME_POS,
    PLAIN_WORD,
    Entry,
    is_form_sense,
    lemma_senses,
    phrase_kind,
    phrase_max_rank,
)


@dataclass(slots=True)
class LexemeSource:
    lexeme_type: LexemeType
    frequency_rank: int | None
    entries: list[Entry] = field(default_factory=list)


@dataclass(slots=True)
class DraftCollector:
    ranks: dict[str, int]
    phrase_top_n: int
    sources: dict[str, LexemeSource] = field(default_factory=dict)
    inflections: dict[str, list[tuple[set[str], set[str]]]] = field(default_factory=dict)
    invalid_lines: int = 0


def inflection_targets(entry: Entry) -> tuple[set[str], set[str]] | None:
    if not entry.senses or not all(is_form_sense(sense) for sense in entry.senses):
        return None
    targets = {
        normalize_text(target.word)
        for sense in entry.senses
        for target in sense.form_of
        if target.word
    }
    tags = {tag for sense in entry.senses for tag in sense.tags if tag != "form-of"}
    return (targets, tags) if targets else None


def add_word(collector: DraftCollector, entry: Entry) -> None:
    key = normalize_text(entry.word)
    if key not in collector.ranks or not PLAIN_WORD.match(key):
        return
    if lemma_senses(entry):
        source = collector.sources.setdefault(
            key, LexemeSource(LexemeType.WORD, collector.ranks[key])
        )
        source.entries.append(entry)
        return
    inflection = inflection_targets(entry)
    if inflection is not None:
        collector.inflections.setdefault(key, []).append(inflection)


def add_phrase(collector: DraftCollector, entry: Entry) -> None:
    max_rank = phrase_max_rank(entry.word, collector.ranks)
    is_importable = (
        phrase_kind(entry) != "other"
        and max_rank is not None
        and max_rank <= collector.phrase_top_n
        and bool(lemma_senses(entry))
    )
    if is_importable:
        key = normalize_text(entry.word)
        collector.sources.setdefault(key, LexemeSource(LexemeType.PHRASE, None)).entries.append(
            entry
        )


def add_entry(collector: DraftCollector, entry: Entry) -> None:
    if entry.lang_code != "en" or entry.pos == NAME_POS:
        return
    if " " in entry.word.strip():
        add_phrase(collector, entry)
    else:
        add_word(collector, entry)


def collect_lexemes(
    lines: Iterable[str], ranks: dict[str, int], phrase_top_n: int
) -> DraftCollector:
    collector = DraftCollector(ranks=ranks, phrase_top_n=phrase_top_n)
    for line in lines:
        if ENGLISH_MARKER not in line:
            continue
        try:
            entry = Entry.model_validate_json(line)
        except ValidationError:
            collector.invalid_lines += 1
            continue
        add_entry(collector, entry)
    return collector
