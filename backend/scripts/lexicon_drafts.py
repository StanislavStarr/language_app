import hashlib
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field

from app.integrations.nlp.normalization import normalize_text
from app.modules.lexicon.enums import LexemeType, PartOfSpeech

from scripts.lexicon_collector import DraftCollector
from scripts.wiktextract import (
    JUNK_FORM_TAGS,
    JUNK_FORMS,
    MAX_MEANINGS_PER_POS,
    US_IPA_TAGS,
    Entry,
    label_matches_gloss,
    label_overlap,
    lemma_senses,
    russian_translations,
)

LETTER = re.compile(r"[a-z]")
MAX_TRANSLATIONS_PER_MEANING = 5
EXTERNAL_ID_LENGTH = 16
POS_ALIASES = {
    "article": PartOfSpeech.DETERMINER,
    "proverb": PartOfSpeech.PHRASE,
    "prep_phrase": PartOfSpeech.PHRASE,
    "adv_phrase": PartOfSpeech.PHRASE,
}


@dataclass(frozen=True, slots=True)
class MeaningDraft:
    part_of_speech: PartOfSpeech
    gloss: str
    sense_order: int
    external_id: str
    translations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormDraft:
    form_normalized: str
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LexemeDraft:
    text: str
    normalized_text: str
    lexeme_type: LexemeType
    ipa: str | None
    audio_url: str | None
    frequency_rank: int | None
    meanings: tuple[MeaningDraft, ...]
    forms: tuple[FormDraft, ...]


@dataclass(slots=True)
class MeaningBuild:
    part_of_speech: PartOfSpeech
    gloss: str
    external_id: str
    translations: list[str] = field(default_factory=list)


def to_part_of_speech(pos: str) -> PartOfSpeech:
    if pos in POS_ALIASES:
        return POS_ALIASES[pos]
    try:
        return PartOfSpeech(pos)
    except ValueError:
        return PartOfSpeech.OTHER


def external_id(part_of_speech: PartOfSpeech, gloss: str) -> str:
    payload = f"{part_of_speech.value}\n{gloss}".encode()
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()[:EXTERNAL_ID_LENGTH]


def translation_targets(
    label: str, targets: list[MeaningBuild], single_sense: bool
) -> list[MeaningBuild]:
    linked = [build for build in targets if label and label_matches_gloss(label, build.gloss)]
    if linked:
        return linked
    overlaps = [(label_overlap(label, build.gloss), build) for build in targets]
    best = max((score for score, _ in overlaps), default=0)
    if best > 0:
        return [build for score, build in overlaps if score == best][:1]
    return targets if single_sense and len(targets) == 1 else []


def attach_translations(entry: Entry, targets: list[MeaningBuild]) -> None:
    for item in russian_translations(entry):
        for build in translation_targets(item.sense, targets, len(lemma_senses(entry)) == 1):
            if (
                item.word not in build.translations
                and len(build.translations) < MAX_TRANSLATIONS_PER_MEANING
            ):
                build.translations.append(item.word)


def select_meanings(entries: list[Entry]) -> list[list[MeaningBuild]]:
    candidates = [
        [
            MeaningBuild(to_part_of_speech(entry.pos), sense.glosses[-1].strip(), "")
            for sense in lemma_senses(entry)
            if sense.glosses[-1].strip()
        ]
        for entry in entries
    ]
    per_pos: dict[PartOfSpeech, int] = defaultdict(int)
    seen: set[str] = set()
    chosen: set[tuple[int, int]] = set()
    for depth in range(max((len(items) for items in candidates), default=0)):
        for entry_index, items in enumerate(candidates):
            if depth >= len(items):
                continue
            build = items[depth]
            identifier = external_id(build.part_of_speech, build.gloss)
            if identifier in seen or per_pos[build.part_of_speech] >= MAX_MEANINGS_PER_POS:
                continue
            seen.add(identifier)
            per_pos[build.part_of_speech] += 1
            build.external_id = identifier
            chosen.add((entry_index, depth))
    return [
        [build for depth, build in enumerate(items) if (entry_index, depth) in chosen]
        for entry_index, items in enumerate(candidates)
    ]


def build_meanings(entries: list[Entry]) -> list[MeaningDraft]:
    selected = select_meanings(entries)
    for entry, builds in zip(entries, selected, strict=True):
        attach_translations(entry, builds)
    ordered = [build for builds in selected for build in builds]
    return [
        MeaningDraft(
            build.part_of_speech, build.gloss, order, build.external_id, tuple(build.translations)
        )
        for order, build in enumerate(ordered, start=1)
    ]


def entry_forms(entry: Entry) -> dict[str, set[str]]:
    forms: dict[str, set[str]] = {}
    for item in entry.forms:
        if not item.form or item.form in JUNK_FORMS or not JUNK_FORM_TAGS.isdisjoint(item.tags):
            continue
        form = normalize_text(item.form)
        if LETTER.search(form):
            forms.setdefault(form, set()).update(item.tags)
    return forms


def pick_ipa(entries: list[Entry]) -> str | None:
    sounds = [sound for entry in entries for sound in entry.sounds if sound.ipa]
    preferred = [sound for sound in sounds if not US_IPA_TAGS.isdisjoint(sound.tags)]
    return (preferred or sounds)[0].ipa if sounds else None


def pick_audio(entries: list[Entry]) -> str | None:
    sounds = [sound for entry in entries for sound in entry.sounds if sound.mp3_url]
    preferred = [sound for sound in sounds if not US_IPA_TAGS.isdisjoint(sound.tags)]
    return (preferred or sounds)[0].mp3_url if sounds else None


def inflected_forms(collector: DraftCollector) -> dict[str, dict[str, set[str]]]:
    by_lemma: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for form, links in collector.inflections.items():
        for targets, tags in links:
            for lemma in targets & collector.sources.keys() - {form}:
                by_lemma[lemma].setdefault(form, set()).update(tags)
    return by_lemma


def build_forms(key: str, entries: list[Entry], inflected: dict[str, set[str]]) -> list[FormDraft]:
    merged: dict[str, set[str]] = {}
    for entry in entries:
        for form, tags in entry_forms(entry).items():
            merged.setdefault(form, set()).update(tags)
    for form, tags in inflected.items():
        merged.setdefault(form, set()).update(tags)
    merged.pop(key, None)
    merged.pop("", None)
    return [FormDraft(form, tuple(sorted(tags))) for form, tags in sorted(merged.items())]


def preferred_entries(key: str, entries: list[Entry]) -> list[Entry]:
    exact = [entry for entry in entries if entry.word == key]
    return exact or entries


def build_drafts(collector: DraftCollector) -> Iterator[LexemeDraft]:
    inflected = inflected_forms(collector)
    for key, source in collector.sources.items():
        entries = preferred_entries(key, source.entries)
        meanings = build_meanings(entries)
        if not meanings:
            continue
        yield LexemeDraft(
            text=entries[0].word,
            normalized_text=key,
            lexeme_type=source.lexeme_type,
            ipa=pick_ipa(entries),
            audio_url=pick_audio(entries),
            frequency_rank=source.frequency_rank,
            meanings=tuple(meanings),
            forms=tuple(build_forms(key, entries, inflected.get(key, {}))),
        )
