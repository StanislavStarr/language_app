from pydantic import BaseModel

from app.integrations.ai.schemas.russian import is_short_russian_text

MAX_MEANINGS_PER_REQUEST = 20
MAX_TRANSLATIONS_PER_MEANING = 3
MAX_TRANSLATION_LENGTH = 60


class TranslatedMeaning(BaseModel):
    meaning_id: int
    translations: list[str]


class TranslationsOutput(BaseModel):
    items: list[TranslatedMeaning]


def check_translations(output: TranslationsOutput, requested_ids: frozenset[int]) -> None:
    returned = [item.meaning_id for item in output.items]
    if len(returned) != len(set(returned)) or set(returned) != requested_ids:
        message = "translations must cover each requested meaning exactly once"
        raise ValueError(message)
    for item in output.items:
        normalized = [text.strip().lower() for text in item.translations]
        if not 1 <= len(normalized) <= MAX_TRANSLATIONS_PER_MEANING:
            message = f"each meaning needs 1-{MAX_TRANSLATIONS_PER_MEANING} translations"
            raise ValueError(message)
        if len(set(normalized)) != len(normalized):
            message = "translations of one meaning must not repeat"
            raise ValueError(message)
        if not all(is_short_russian_text(text, MAX_TRANSLATION_LENGTH) for text in normalized):
            message = "each translation must be a short Russian text"
            raise ValueError(message)
