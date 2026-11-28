import gzip
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, TextIO

from pydantic import BaseModel, ConfigDict, Field
from wordfreq import top_n_list

ENGLISH_MARKER = '"lang_code": "en"'
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


def tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def is_form_sense(sense: Sense) -> bool:
    return bool(sense.form_of) or "form-of" in sense.tags


def label_tokens(label: str) -> set[str]:
    return {token for token in tokens(label) if len(token) >= MIN_LABEL_TOKEN_LENGTH}


def label_matches_gloss(label: str, gloss: str) -> bool:
    wanted = label_tokens(label)
    return bool(wanted) and wanted <= set(tokens(gloss))


def label_overlap(label: str, gloss: str) -> int:
    return len(label_tokens(label) & set(tokens(gloss)))


def russian_translations(entry: Entry) -> list[Translation]:
    return [item for item in entry.translations if item.lang_code == RUSSIAN and item.word]


def lemma_senses(entry: Entry) -> list[Sense]:
    return [sense for sense in entry.senses if sense.glosses and not is_form_sense(sense)]


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


def open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def read_lines(path: Path, max_lines: int | None) -> Iterator[str]:
    with open_text(path) as source:
        for index, line in enumerate(source):
            if max_lines is not None and index >= max_lines:
                return
            yield line


def build_ranks(top_n: int) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for rank, word in enumerate(top_n_list("en", top_n), start=1):
        ranks.setdefault(word.lower(), rank)
    return ranks
