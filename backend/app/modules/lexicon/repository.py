from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.lexicon.enums import LexemeType, LexiconSource, PartOfSpeech, TranslationSource
from app.modules.lexicon.models import (
    Lexeme,
    LexemeForm,
    Meaning,
    SenseSelection,
    Translation,
)


@dataclass(frozen=True, slots=True)
class LexemeMatch:
    lexeme: Lexeme
    candidate: str
    matched_by_form: bool


@dataclass(frozen=True, slots=True)
class SimilarLexeme:
    lexeme: Lexeme
    similarity: float


@dataclass(frozen=True, slots=True)
class NewLexeme:
    language_id: int
    text: str
    normalized_text: str
    lexeme_type: LexemeType
    ipa: str | None
    audio_url: str | None
    source: LexiconSource


@dataclass(frozen=True, slots=True)
class NewMeaning:
    part_of_speech: PartOfSpeech
    gloss: str


@dataclass(frozen=True, slots=True)
class NewTranslation:
    meaning_id: int
    language_id: int
    text: str


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

    async def get(self, lexeme_id: int) -> Lexeme | None:
        return await self._session.get(Lexeme, lexeme_id)

    async def parts_of_speech(self, lexeme_ids: Sequence[int]) -> dict[int, set[PartOfSpeech]]:
        rows = await self._session.execute(
            select(Meaning.lexeme_id, Meaning.part_of_speech)
            .where(Meaning.lexeme_id.in_(lexeme_ids))
            .distinct()
        )
        result: dict[int, set[PartOfSpeech]] = {lexeme_id: set() for lexeme_id in lexeme_ids}
        for lexeme_id, part_of_speech in rows:
            result[lexeme_id].add(part_of_speech)
        return result

    async def create_lexeme(self, new: NewLexeme) -> Lexeme | None:
        statement = (
            insert(Lexeme)
            .values(
                language_id=new.language_id,
                text=new.text,
                normalized_text=new.normalized_text,
                type=new.lexeme_type,
                ipa=new.ipa,
                audio_url=new.audio_url,
                source=new.source,
            )
            .on_conflict_do_nothing(index_elements=[Lexeme.language_id, Lexeme.normalized_text])
            .returning(Lexeme.id)
        )
        lexeme_id = await self._session.scalar(statement)
        return await self.get(lexeme_id) if lexeme_id is not None else None

    async def find_exact(self, language_id: int, normalized_text: str) -> Lexeme | None:
        return await self._session.scalar(
            select(Lexeme).where(
                Lexeme.language_id == language_id, Lexeme.normalized_text == normalized_text
            )
        )

    async def lock_meanings(self, lexeme_id: int) -> None:
        await self._session.execute(select(func.pg_advisory_xact_lock(lexeme_id)))

    async def last_sense_order(self, lexeme_id: int) -> int:
        highest = await self._session.scalar(
            select(func.max(Meaning.sense_order)).where(Meaning.lexeme_id == lexeme_id)
        )
        return highest or 0

    async def add_meanings(
        self, lexeme_id: int, source: LexiconSource, meanings: Sequence[NewMeaning]
    ) -> list[Meaning]:
        first_order = await self.last_sense_order(lexeme_id) + 1
        created = [
            Meaning(
                lexeme_id=lexeme_id,
                part_of_speech=meaning.part_of_speech,
                gloss=meaning.gloss,
                sense_order=first_order + offset,
                source=source,
            )
            for offset, meaning in enumerate(meanings)
        ]
        self._session.add_all(created)
        await self._session.flush()
        return created

    async def add_translations(
        self, source: TranslationSource, translations: Sequence[NewTranslation]
    ) -> None:
        if not translations:
            return
        statement = insert(Translation).on_conflict_do_nothing(
            index_elements=[Translation.meaning_id, Translation.language_id, Translation.text]
        )
        await self._session.execute(
            statement,
            [
                {
                    "meaning_id": item.meaning_id,
                    "language_id": item.language_id,
                    "text": item.text,
                    "source": source,
                }
                for item in translations
            ],
        )

    async def find_sense_selection(
        self, lexeme_id: int, context_hash: str, prompt_version: str
    ) -> SenseSelection | None:
        return await self._session.scalar(
            select(SenseSelection).where(
                SenseSelection.lexeme_id == lexeme_id,
                SenseSelection.context_hash == context_hash,
                SenseSelection.prompt_version == prompt_version,
            )
        )

    async def save_sense_selection(self, selection: SenseSelection) -> None:
        statement = (
            insert(SenseSelection)
            .values(
                lexeme_id=selection.lexeme_id,
                context_hash=selection.context_hash,
                selected_meaning_id=selection.selected_meaning_id,
                contextual_translation=selection.contextual_translation,
                confidence=selection.confidence,
                model=selection.model,
                prompt_version=selection.prompt_version,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    SenseSelection.lexeme_id,
                    SenseSelection.context_hash,
                    SenseSelection.prompt_version,
                ]
            )
        )
        await self._session.execute(statement)
