from collections.abc import Sequence

import structlog

from app.integrations.ai.provider import AIProvider, GenerateFallbackMeaningsRequest
from app.integrations.dictionary.provider import DictionaryError, DictionaryProvider
from app.modules.lexicon.ai_calls import call_with_one_retry
from app.modules.lexicon.enums import LexemeType, LexiconSource, PartOfSpeech
from app.modules.lexicon.lookup_target import LookupTarget
from app.modules.lexicon.models import Lexeme
from app.modules.lexicon.part_of_speech import to_part_of_speech
from app.modules.lexicon.repository import LexemeRepository, NewLexeme, NewMeaning

MAX_MEANINGS_PER_POS = 8

logger = structlog.get_logger()


def meaning_key(part_of_speech: PartOfSpeech, gloss: str) -> tuple[PartOfSpeech, str]:
    return part_of_speech, gloss.casefold()


def limited(meanings: Sequence[NewMeaning]) -> list[NewMeaning]:
    per_pos: dict[PartOfSpeech, int] = {}
    seen: set[tuple[PartOfSpeech, str]] = set()
    kept: list[NewMeaning] = []
    for meaning in meanings:
        key = meaning_key(meaning.part_of_speech, meaning.gloss)
        if key in seen or per_pos.get(meaning.part_of_speech, 0) >= MAX_MEANINGS_PER_POS:
            continue
        seen.add(key)
        per_pos[meaning.part_of_speech] = per_pos.get(meaning.part_of_speech, 0) + 1
        kept.append(meaning)
    return kept


class LexemeSources:
    def __init__(
        self, repository: LexemeRepository, dictionary: DictionaryProvider, language_id: int
    ) -> None:
        self._repository = repository
        self._dictionary = dictionary
        self._language_id = language_id

    async def from_dictionary(self, target: LookupTarget) -> Lexeme | None:
        for candidate in target.candidates:
            try:
                entry = await self._dictionary.lookup(candidate)
            except DictionaryError:
                logger.warning("dictionary_degraded")
                return None
            if entry is None:
                continue
            meanings = [
                NewMeaning(to_part_of_speech(item.part_of_speech), item.definition)
                for item in entry.meanings
            ]
            lexeme_type = LexemeType.PHRASE if " " in candidate else LexemeType.WORD
            new = NewLexeme(
                self._language_id,
                candidate,
                candidate,
                lexeme_type,
                entry.ipa,
                entry.audio_url,
                LexiconSource.FREE_DICTIONARY,
            )
            return await self._store(new, limited(meanings))
        return None

    async def from_ai(self, provider: AIProvider, target: LookupTarget) -> Lexeme | None:
        request = GenerateFallbackMeaningsRequest(target.text, target.sentence)
        result = await call_with_one_retry(
            "fallback_meanings", lambda: provider.generate_fallback_meanings(request)
        )
        if result is None or not result.value.found:
            return None
        meanings = [
            NewMeaning(to_part_of_speech(item.part_of_speech), item.gloss.strip())
            for item in result.value.meanings
        ]
        new = NewLexeme(
            self._language_id,
            target.text,
            target.text,
            target.lexeme_type,
            None,
            None,
            LexiconSource.AI,
        )
        return await self._store(new, limited(meanings))

    async def _store(self, new: NewLexeme, meanings: list[NewMeaning]) -> Lexeme | None:
        if not meanings:
            return None
        created = await self._repository.create_lexeme(new)
        if created is None:
            return await self._repository.find_exact(new.language_id, new.normalized_text)
        await self._repository.add_meanings(created.id, new.source, meanings)
        return created
