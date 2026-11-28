from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.lexicon.models import Lexeme, LexemeForm, Meaning, Translation


@dataclass(frozen=True, slots=True)
class LexemeMatch:
    lexeme: Lexeme
    candidate: str
    matched_by_form: bool


@dataclass(frozen=True, slots=True)
class SimilarLexeme:
    lexeme: Lexeme
    similarity: float


class LexemeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_candidates(
        self, language_id: int, candidates: Sequence[str]
    ) -> list[LexemeMatch]:
        if not candidates:
            return []
        by_text = await self._session.scalars(
            select(Lexeme).where(
                Lexeme.language_id == language_id, Lexeme.normalized_text.in_(candidates)
            )
        )
        by_form = await self._session.execute(
            select(Lexeme, LexemeForm.form_normalized)
            .join(LexemeForm, LexemeForm.lexeme_id == Lexeme.id)
            .where(Lexeme.language_id == language_id, LexemeForm.form_normalized.in_(candidates))
        )
        matches = [LexemeMatch(lexeme, lexeme.normalized_text, False) for lexeme in by_text]
        matches += [LexemeMatch(lexeme, form, True) for lexeme, form in by_form]
        priority = {candidate: index for index, candidate in enumerate(candidates)}
        return sorted(
            matches,
            key=lambda match: (
                priority[match.candidate],
                match.matched_by_form,
                match.lexeme.frequency_rank is None,
                match.lexeme.frequency_rank or 0,
                match.lexeme.id,
            ),
        )

    async def list_meanings(
        self, lexeme_id: int, translation_language_id: int, offset: int, limit: int
    ) -> list[Meaning]:
        statement = (
            select(Meaning)
            .where(Meaning.lexeme_id == lexeme_id)
            .order_by(Meaning.sense_order, Meaning.id)
            .offset(offset)
            .limit(limit)
            .options(
                selectinload(
                    Meaning.translations.and_(Translation.language_id == translation_language_id)
                )
            )
        )
        return list(await self._session.scalars(statement))

    async def find_similar(
        self, language_id: int, normalized_text: str, threshold: float, limit: int
    ) -> list[SimilarLexeme]:
        await self._session.execute(
            select(func.set_config("pg_trgm.similarity_threshold", str(threshold), True))
        )
        similarity = func.similarity(Lexeme.normalized_text, normalized_text)
        statement = (
            select(Lexeme, similarity.label("similarity"))
            .where(
                Lexeme.language_id == language_id,
                Lexeme.normalized_text.op("%")(normalized_text),
            )
            .order_by(
                similarity.desc(),
                Lexeme.frequency_rank.asc().nulls_last(),
                Lexeme.id,
            )
            .limit(limit)
        )
        rows = await self._session.execute(statement)
        return [SimilarLexeme(lexeme, score) for lexeme, score in rows]
