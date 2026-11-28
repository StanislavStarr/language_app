from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.ai.provider import AIProvider, GenerateFallbackMeaningsRequest
from app.integrations.dictionary.provider import DictionaryProvider
from app.integrations.nlp.provider import TextAnalyzer
from app.modules.languages.models import Language
from app.modules.languages.service import LanguageService
from app.modules.lexicon.ai_access import AiAccess
from app.modules.lexicon.ai_calls import call_with_one_retry
from app.modules.lexicon.enums import LexiconSource
from app.modules.lexicon.exceptions import AiTemporarilyUnavailableError, LexemeNotFoundError
from app.modules.lexicon.lexeme_sources import LexemeSources, limited, meaning_key
from app.modules.lexicon.lookup_target import LookupTarget, build_target
from app.modules.lexicon.meaning_translator import MeaningTranslator
from app.modules.lexicon.models import Lexeme, Meaning
from app.modules.lexicon.part_of_speech import to_part_of_speech
from app.modules.lexicon.repository import LexemeMatch, LexemeRepository, NewMeaning
from app.modules.lexicon.schemas import (
    MEANINGS_PAGE_SIZE,
    AiMeaningsRequest,
    LexemeResponse,
    LookupResponse,
    ManualLookup,
    MeaningResponse,
    MeaningsPage,
    RecommendedMeaning,
)
from app.modules.lexicon.sense_choice import SenseChooser
from app.modules.usage.enums import UsageKind
from app.modules.usage.service import UsageService

TYPO_SIMILARITY_THRESHOLD = 0.45
MAX_LEXEME_MEANINGS = 50


@dataclass(frozen=True, slots=True)
class LexiconProviders:
    analyzer: TextAnalyzer
    dictionary: DictionaryProvider
    ai: AIProvider | None


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


class LookupService:
    def __init__(
        self,
        session: AsyncSession,
        repository: LexemeRepository,
        providers: LexiconProviders,
        usage: UsageService,
        languages: LanguageService,
    ) -> None:
        self._session = session
        self._repository = repository
        self._providers = providers
        self._usage = usage
        self._languages = languages

    async def lookup(self, user_id: UUID, request: ManualLookup) -> LookupResponse:
        english = await self._languages.get_language_by_code("en")
        russian = await self._languages.get_language_by_code("ru")
        target = await build_target(
            self._providers.analyzer, request.text, request.context_sentence
        )
        ai = AiAccess(self._providers.ai, self._usage, user_id)
        sources = LexemeSources(self._repository, self._providers.dictionary, english.id)
        lexeme = await self._find_lexeme(english, target) or await sources.from_dictionary(target)
        typo: str | None = None
        if lexeme is None:
            typo = await self._typo_suggestion(english, target)
            provider = await ai.provider() if typo is None else None
            if provider is not None:
                lexeme = await sources.from_ai(provider, target)
        response = await self._respond(lexeme, target, ai, russian, typo)
        await self._session.commit()
        return response

    async def list_meanings(self, lexeme_id: int, offset: int, limit: int) -> MeaningsPage:
        await self._require_lexeme(lexeme_id)
        russian = await self._languages.get_language_by_code("ru")
        meanings = await self._repository.list_meanings(lexeme_id, russian.id, offset, limit + 1)
        return MeaningsPage(
            meanings=[to_meaning_response(meaning) for meaning in meanings[:limit]],
            has_more=len(meanings) > limit,
        )

    async def generate_ai_meanings(
        self, user_id: UUID, lexeme_id: int, request: AiMeaningsRequest
    ) -> MeaningsPage:
        lexeme = await self._require_lexeme(lexeme_id)
        provider = self._providers.ai
        if provider is None:
            raise AiTemporarilyUnavailableError
        await self._usage.consume(user_id, UsageKind.AI_LOOKUP)
        result = await call_with_one_retry(
            "fallback_meanings",
            lambda: provider.generate_fallback_meanings(
                GenerateFallbackMeaningsRequest(lexeme.text, request.context_sentence)
            ),
        )
        if result is None:
            raise AiTemporarilyUnavailableError
        russian = await self._languages.get_language_by_code("ru")
        await self._repository.lock_meanings(lexeme_id)
        existing = await self._repository.list_meanings(
            lexeme_id, russian.id, 0, MAX_LEXEME_MEANINGS
        )
        known = {meaning_key(meaning.part_of_speech, meaning.gloss) for meaning in existing}
        fresh = [
            meaning
            for meaning in limited(
                [
                    NewMeaning(to_part_of_speech(item.part_of_speech), item.gloss.strip())
                    for item in result.value.meanings
                ]
            )
            if meaning_key(meaning.part_of_speech, meaning.gloss) not in known
        ]
        created = await self._repository.add_meanings(lexeme_id, LexiconSource.AI, fresh)
        translations = await MeaningTranslator(self._repository, russian.id).translate(
            provider, lexeme, created
        )
        await self._session.commit()
        return MeaningsPage(
            meanings=[
                MeaningResponse(
                    id=meaning.id,
                    part_of_speech=meaning.part_of_speech,
                    gloss=meaning.gloss,
                    translations=translations.get(meaning.id, []),
                )
                for meaning in created
            ],
            has_more=False,
        )

    async def _require_lexeme(self, lexeme_id: int) -> Lexeme:
        lexeme = await self._repository.get(lexeme_id)
        if lexeme is None:
            raise LexemeNotFoundError(lexeme_id)
        return lexeme

    async def _find_lexeme(self, english: Language, target: LookupTarget) -> Lexeme | None:
        matches = await self._repository.find_by_candidates(english.id, target.candidates)
        if not matches:
            return None
        best = [match for match in matches if match.candidate == matches[0].candidate]
        group = list({match.lexeme.id: match for match in best}.values())
        if len(group) > 1 and target.part_of_speech is not None:
            return await self._prefer_part_of_speech(group, target)
        return group[0].lexeme

    async def _prefer_part_of_speech(
        self, group: Sequence[LexemeMatch], target: LookupTarget
    ) -> Lexeme:
        parts = await self._repository.parts_of_speech([match.lexeme.id for match in group])
        for match in group:
            if target.part_of_speech in parts[match.lexeme.id]:
                return match.lexeme
        return group[0].lexeme

    async def _typo_suggestion(self, english: Language, target: LookupTarget) -> str | None:
        similar = await self._repository.find_similar(
            english.id, target.text, TYPO_SIMILARITY_THRESHOLD, 1
        )
        return similar[0].lexeme.text if similar else None

    async def _respond(
        self,
        lexeme: Lexeme | None,
        target: LookupTarget,
        ai: AiAccess,
        russian: Language,
        typo: str | None,
    ) -> LookupResponse:
        if lexeme is None:
            return LookupResponse(
                lexeme=None,
                recommended=None,
                meanings=[],
                has_more=False,
                user_meaning_ids=[],
                typo_suggestion=typo,
                ai_limited=ai.limit_exceeded,
            )
        meanings = await self._repository.list_meanings(
            lexeme.id, russian.id, 0, MAX_LEXEME_MEANINGS
        )
        recommended = None
        if len(meanings) > 1:
            recommended = await SenseChooser(self._repository).choose(ai, lexeme, meanings, target)
        shown = recommended_first(meanings, recommended)[:MEANINGS_PAGE_SIZE]
        added = await self._translate_missing(ai, lexeme, shown, russian)
        return LookupResponse(
            lexeme=LexemeResponse(
                id=lexeme.id,
                text=target.text,
                lemma=lexeme.text,
                ipa=lexeme.ipa,
                audio_url=lexeme.audio_url,
            ),
            recommended=recommended,
            meanings=[to_meaning_response(meaning, added.get(meaning.id, ())) for meaning in shown],
            has_more=len(meanings) > MEANINGS_PAGE_SIZE,
            user_meaning_ids=[],
            typo_suggestion=None,
            ai_limited=ai.limit_exceeded,
        )

    async def _translate_missing(
        self, ai: AiAccess, lexeme: Lexeme, shown: Sequence[Meaning], russian: Language
    ) -> dict[int, list[str]]:
        missing = [meaning for meaning in shown if not meaning.translations]
        provider = await ai.provider() if missing else None
        if provider is None:
            return {}
        return await MeaningTranslator(self._repository, russian.id).translate(
            provider, lexeme, missing
        )
