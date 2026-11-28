from typing import Literal

from pydantic import BaseModel

from app.integrations.ai.schemas.words import contains_any

MAX_FALLBACK_MEANINGS = 4
MIN_GLOSS_LENGTH = 5
MAX_GLOSS_LENGTH = 200

type PartOfSpeechName = Literal[
    "noun",
    "verb",
    "adj",
    "adv",
    "pron",
    "prep",
    "conj",
    "det",
    "intj",
    "num",
    "particle",
    "phrase",
    "other",
]


class FallbackMeaning(BaseModel):
    part_of_speech: PartOfSpeechName
    gloss: str


class FallbackMeaningsOutput(BaseModel):
    found: bool
    meanings: list[FallbackMeaning]


def check_fallback_meanings(output: FallbackMeaningsOutput, target_word: str) -> None:
    if output.found != bool(output.meanings):
        message = "found must be true exactly when meanings are present"
        raise ValueError(message)
    if len(output.meanings) > MAX_FALLBACK_MEANINGS:
        message = f"at most {MAX_FALLBACK_MEANINGS} meanings are allowed"
        raise ValueError(message)
    for meaning in output.meanings:
        if not MIN_GLOSS_LENGTH <= len(meaning.gloss.strip()) <= MAX_GLOSS_LENGTH:
            message = f"a gloss must be {MIN_GLOSS_LENGTH}-{MAX_GLOSS_LENGTH} characters long"
            raise ValueError(message)
        if contains_any(meaning.gloss, (target_word,)):
            message = "a gloss must not contain the target word"
            raise ValueError(message)
