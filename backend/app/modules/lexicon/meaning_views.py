from collections.abc import Sequence

from app.modules.lexicon.models import Meaning
from app.modules.lexicon.schemas import MeaningResponse, RecommendedMeaning


def to_meaning_response(meaning: Meaning, extra: Sequence[str] = ()) -> MeaningResponse:
    texts = [translation.text for translation in meaning.translations]
    return MeaningResponse(
        id=meaning.id,
        part_of_speech=meaning.part_of_speech,
        gloss=meaning.gloss,
        translations=[*texts, *(text for text in extra if text not in texts)],
    )


def recommended_first(
    meanings: Sequence[Meaning], recommended: RecommendedMeaning | None
) -> list[Meaning]:
    if recommended is None:
        return list(meanings)
    first = [meaning for meaning in meanings if meaning.id == recommended.meaning_id]
    return first + [meaning for meaning in meanings if meaning.id != recommended.meaning_id]
