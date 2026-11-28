from collections.abc import Sequence

from app.integrations.ai.provider import AIProvider, SenseCandidate, TranslateMeaningsRequest
from app.modules.lexicon.ai_calls import call_unless_unavailable, call_with_one_retry
from app.modules.lexicon.enums import TranslationSource
from app.modules.lexicon.models import Lexeme, Meaning
from app.modules.lexicon.repository import LexemeRepository, NewTranslation


class MeaningTranslator:
    def __init__(
        self, repository: LexemeRepository, russian_id: int, *, raise_when_unavailable: bool = False
    ) -> None:
        self._repository = repository
        self._russian_id = russian_id
        self._call = call_unless_unavailable if raise_when_unavailable else call_with_one_retry

    async def translate(
        self, provider: AIProvider, lexeme: Lexeme, meanings: Sequence[Meaning]
    ) -> dict[int, list[str]]:
        if not meanings:
            return {}
        request = TranslateMeaningsRequest(
            lexeme.text,
            tuple(
                SenseCandidate(meaning.id, meaning.part_of_speech.value, meaning.gloss)
                for meaning in meanings
            ),
        )
        result = await self._call(
            "translate_meanings", lambda: provider.translate_meanings(request)
        )
        if result is None:
            return {}
        translated = {
            item.meaning_id: list(dict.fromkeys(text.strip().lower() for text in item.translations))
            for item in result.value.items
        }
        await self._repository.add_translations(
            TranslationSource.AI,
            [
                NewTranslation(meaning_id, self._russian_id, text)
                for meaning_id, texts in translated.items()
                for text in texts
            ],
        )
        return translated
