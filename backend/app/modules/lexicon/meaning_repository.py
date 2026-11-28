from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.nlp.normalization import normalize_text
from app.modules.lexicon.models import (
    IrregularVerb,
    Lexeme,
    LexemeForm,
    Meaning,
    MeaningContent,
    Translation,
)


@dataclass(frozen=True, slots=True)
class MeaningDetails:
    meaning: Meaning
    lexeme: Lexeme
    translations: list[str]
    content: MeaningContent | None


class MeaningRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists(self, meaning_id: int) -> bool:
        found = await self._session.scalar(select(Meaning.id).where(Meaning.id == meaning_id))
        return found is not None

    async def details(
        self, meaning_ids: Sequence[int], language_id: int, content_ids: Sequence[int]
    ) -> dict[int, MeaningDetails]:
        if not meaning_ids:
            return {}
        rows = await self._session.execute(
            select(Meaning, Lexeme)
            .join(Lexeme, Lexeme.id == Meaning.lexeme_id)
            .where(Meaning.id.in_(meaning_ids))
        )
        translations = await self._translations(meaning_ids, language_id)
        contents = await self._contents(content_ids)
        content_by_meaning = {content.meaning_id: content for content in contents}
        return {
            meaning.id: MeaningDetails(
                meaning,
                lexeme,
                translations.get(meaning.id, []),
                content_by_meaning.get(meaning.id),
            )
            for meaning, lexeme in rows
        }

    async def forms(self, meaning_ids: Sequence[int], limit: int) -> list[str]:
        if not meaning_ids:
            return []
        lexeme_ids = select(Meaning.lexeme_id).where(Meaning.id.in_(meaning_ids)).distinct()
        texts = await self._session.scalars(
            select(Lexeme.normalized_text).where(Lexeme.id.in_(lexeme_ids))
        )
        derived = await self._session.scalars(
            select(LexemeForm.form_normalized)
            .where(LexemeForm.lexeme_id.in_(lexeme_ids))
            .limit(limit)
        )
        irregular = await self._session.execute(
            select(IrregularVerb.past_simple, IrregularVerb.past_participle).where(
                IrregularVerb.base_lexeme_id.in_(lexeme_ids)
            )
        )
        forms = [*texts, *derived]
        for past_simple, past_participle in irregular:
            forms.extend(
                normalize_text(part)
                for value in (past_simple, past_participle)
                for part in value.split("/")
            )
        return sorted({form for form in forms if form})[:limit]

    async def _translations(
        self, meaning_ids: Sequence[int], language_id: int
    ) -> dict[int, list[str]]:
        rows = await self._session.execute(
            select(Translation.meaning_id, Translation.text)
            .where(Translation.meaning_id.in_(meaning_ids), Translation.language_id == language_id)
            .order_by(Translation.id)
        )
        result: dict[int, list[str]] = {}
        for meaning_id, text in rows:
            result.setdefault(meaning_id, []).append(text)
        return result

    async def _contents(self, content_ids: Sequence[int]) -> list[MeaningContent]:
        if not content_ids:
            return []
        return list(
            await self._session.scalars(
                select(MeaningContent).where(MeaningContent.id.in_(content_ids))
            )
        )
