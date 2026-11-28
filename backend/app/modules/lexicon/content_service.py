from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.ai.prompts.meaning_content import PROMPT_VERSION
from app.integrations.ai.provider import (
    AIProvider,
    AIUnavailableError,
    GenerateMeaningContentRequest,
)
from app.modules.languages.enums import CefrLevel
from app.modules.lexicon.ai_calls import call_unless_unavailable
from app.modules.lexicon.enums import MeaningContentStatus
from app.modules.lexicon.exceptions import MeaningNotFoundError
from app.modules.lexicon.meaning_repository import MeaningRepository
from app.modules.lexicon.meaning_translator import MeaningTranslator
from app.modules.lexicon.models import MeaningContent
from app.modules.lexicon.repository import LexemeRepository

MAX_FORMS_IN_PROMPT = 50


class MeaningContentService:
    def __init__(
        self, session: AsyncSession, lexemes: LexemeRepository, meanings: MeaningRepository
    ) -> None:
        self._session = session
        self._lexemes = lexemes
        self._meanings = meanings

    async def has_translation(self, meaning_id: int, language_id: int) -> bool:
        return await self._meanings.has_translation(meaning_id, language_id)

    async def ready_content_id(self, meaning_id: int, cefr_level: CefrLevel) -> int | None:
        content = await self._meanings.find_content(meaning_id, cefr_level, PROMPT_VERSION)
        return content.id if content and content.status == MeaningContentStatus.READY else None

    async def translate(self, meaning_id: int, language_id: int, provider: AIProvider) -> bool:
        found = await self._meanings.meaning_with_lexeme(meaning_id)
        if found is None:
            raise MeaningNotFoundError(meaning_id)
        meaning, lexeme = found
        await self._meanings.advisory_lock(f"translation:{meaning_id}:{language_id}")
        if await self._meanings.has_translation(meaning_id, language_id):
            await self._session.commit()
            return True
        translator = MeaningTranslator(self._lexemes, language_id, raise_when_unavailable=True)
        translated = await translator.translate(provider, lexeme, [meaning])
        await self._session.commit()
        return bool(translated.get(meaning_id))

    async def ensure_content(
        self, meaning_id: int, cefr_level: CefrLevel, provider: AIProvider
    ) -> int | None:
        found = await self._meanings.meaning_with_lexeme(meaning_id)
        if found is None:
            raise MeaningNotFoundError(meaning_id)
        meaning, lexeme = found
        await self._meanings.advisory_lock(f"meaning_content:{meaning_id}:{cefr_level.value}")
        existing = await self._meanings.find_content(meaning_id, cefr_level, PROMPT_VERSION)
        if existing is not None and existing.status == MeaningContentStatus.READY:
            await self._session.commit()
            return existing.id
        forms = await self._meanings.forms([meaning_id], MAX_FORMS_IN_PROMPT)
        request = GenerateMeaningContentRequest(
            lexeme.text,
            tuple(forms),
            meaning.part_of_speech.value,
            meaning.gloss,
            cefr_level.value,
        )
        try:
            result = await call_unless_unavailable(
                "meaning_content", lambda: provider.generate_meaning_content(request)
            )
        except AIUnavailableError:
            await self._session.rollback()
            raise
        if result is None:
            await self._session.commit()
            return None
        content = existing or MeaningContent(meaning_id=meaning_id, cefr_level=cefr_level)
        content.definition = result.value.definition.strip()
        content.example = result.value.example.strip()
        content.status = MeaningContentStatus.READY
        content.provider = type(provider).__name__
        content.model = result.model
        content.prompt_version = result.prompt_version
        content.generated_at = datetime.now(UTC)
        if existing is None:
            self._meanings.add_content(content)
        await self._session.commit()
        return content.id


def build_meaning_content_service(session: AsyncSession) -> MeaningContentService:
    return MeaningContentService(session, LexemeRepository(session), MeaningRepository(session))
