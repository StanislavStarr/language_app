from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.ai.provider import AIProvider, AIUnavailableError
from app.modules.languages.enums import CefrLevel
from app.modules.lexicon.content_service import (
    MeaningContentService,
    build_meaning_content_service,
)
from app.modules.users.models import User
from app.modules.users.service import UserService, build_user_service
from app.modules.vocabulary.enrichment_status import (
    EnrichmentTarget,
    VocabularyEnrichment,
    build_vocabulary_enrichment,
)
from app.modules.vocabulary.enums import EnrichmentStatus


def final_status(has_translation: bool, has_content: bool) -> EnrichmentStatus:
    if has_translation and has_content:
        return EnrichmentStatus.READY
    if has_translation or has_content:
        return EnrichmentStatus.PARTIAL
    return EnrichmentStatus.FAILED


class EnrichmentService:
    def __init__(
        self,
        vocabulary: VocabularyEnrichment,
        users: UserService,
        content: MeaningContentService,
        provider: AIProvider | None,
    ) -> None:
        self._vocabulary = vocabulary
        self._users = users
        self._content = content
        self._provider = provider

    async def enrich_item(self, item_id: UUID, *, final_attempt: bool) -> None:
        target = await self._vocabulary.begin(item_id)
        if target is None:
            return
        user = await self._users.find_user(target.user_id)
        if user is None:
            return
        has_translation = await self._translation(target, user, final_attempt)
        content_id = await self._content_id(target, user.cefr_level, final_attempt)
        await self._vocabulary.finish(
            item_id, final_status(has_translation, content_id is not None), content_id
        )

    async def abandon(self, item_id: UUID) -> None:
        target = await self._vocabulary.begin(item_id)
        if target is None:
            return
        user = await self._users.find_user(target.user_id)
        if user is None:
            return
        has_translation = await self._content.has_translation(
            target.meaning_id, user.native_language_id
        )
        content_id = await self._content.ready_content_id(target.meaning_id, user.cefr_level)
        await self._vocabulary.finish(
            item_id, final_status(has_translation, content_id is not None), content_id
        )

    async def _translation(self, target: EnrichmentTarget, user: User, final_attempt: bool) -> bool:
        language_id = user.native_language_id
        if await self._content.has_translation(target.meaning_id, language_id):
            return True
        if self._provider is None:
            return False
        try:
            return await self._content.translate(target.meaning_id, language_id, self._provider)
        except AIUnavailableError:
            if not final_attempt:
                raise
            return False

    async def _content_id(
        self, target: EnrichmentTarget, cefr_level: CefrLevel, final_attempt: bool
    ) -> int | None:
        existing = await self._content.ready_content_id(target.meaning_id, cefr_level)
        if existing is not None or self._provider is None:
            return existing
        try:
            return await self._content.ensure_content(target.meaning_id, cefr_level, self._provider)
        except AIUnavailableError:
            if not final_attempt:
                raise
            return None


def build_enrichment_service(
    session: AsyncSession, provider: AIProvider | None
) -> EnrichmentService:
    return EnrichmentService(
        build_vocabulary_enrichment(session),
        build_user_service(session),
        build_meaning_content_service(session),
        provider,
    )
