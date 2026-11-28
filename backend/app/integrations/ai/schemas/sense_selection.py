from pydantic import BaseModel

from app.integrations.ai.schemas.russian import is_short_russian_text

MAX_CONTEXTUAL_TRANSLATION_LENGTH = 80


class SenseSelectionOutput(BaseModel):
    selected_meaning_id: int | None
    contextual_translation: str | None
    confidence: float


def check_sense_selection(output: SenseSelectionOutput, candidate_ids: frozenset[int]) -> None:
    if not 0 <= output.confidence <= 1:
        message = "confidence must be between 0 and 1"
        raise ValueError(message)
    if output.selected_meaning_id is not None and output.selected_meaning_id not in candidate_ids:
        message = "selected_meaning_id is not one of the candidates"
        raise ValueError(message)
    if output.selected_meaning_id is None and output.contextual_translation is not None:
        message = "contextual_translation must be null when no meaning is selected"
        raise ValueError(message)
    translation = output.contextual_translation
    if translation is not None and not is_short_russian_text(
        translation, MAX_CONTEXTUAL_TRANSLATION_LENGTH
    ):
        message = "contextual_translation must be a short Russian text"
        raise ValueError(message)
