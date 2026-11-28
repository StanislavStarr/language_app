from collections.abc import Sequence
from dataclasses import dataclass, fields

from app.modules.lexicon.enums import LexiconSource, TranslationSource
from app.modules.lexicon.models import Lexeme, LexemeForm, Meaning, Translation
from sqlalchemy import Boolean, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.lexicon_drafts import LexemeDraft

INSERTED = literal_column("(xmax = 0)", Boolean).label("inserted")


@dataclass(slots=True)
class LoadCounts:
    lexemes_inserted: int = 0
    lexemes_updated: int = 0
    meanings_inserted: int = 0
    meanings_updated: int = 0
    translations_inserted: int = 0
    forms_inserted: int = 0
    forms_updated: int = 0

    def add(self, other: "LoadCounts") -> None:
        for item in fields(self):
            setattr(self, item.name, getattr(self, item.name) + getattr(other, item.name))


class LexiconBatchLoader:
    def __init__(self, session: AsyncSession, english_id: int, russian_id: int) -> None:
        self._session = session
        self._english_id = english_id
        self._russian_id = russian_id
        self.counts = LoadCounts()

    async def load(self, drafts: Sequence[LexemeDraft]) -> LoadCounts:
        lexeme_ids = await self._upsert_lexemes(drafts)
        meaning_ids = await self._upsert_meanings(drafts, lexeme_ids)
        await self._insert_translations(drafts, lexeme_ids, meaning_ids)
        await self._upsert_forms(drafts, lexeme_ids)
        return self.counts

    async def _upsert_lexemes(self, drafts: Sequence[LexemeDraft]) -> dict[str, int]:
        base = insert(Lexeme)
        merged = {
            "text": base.excluded.text,
            "type": base.excluded.type,
            "ipa": func.coalesce(base.excluded.ipa, Lexeme.ipa),
            "audio_url": func.coalesce(base.excluded.audio_url, Lexeme.audio_url),
            "frequency_rank": func.coalesce(base.excluded.frequency_rank, Lexeme.frequency_rank),
            "source": base.excluded.source,
        }
        statement = base.on_conflict_do_update(
            index_elements=[Lexeme.language_id, Lexeme.normalized_text],
            set_={**merged, "updated_at": func.now()},
            where=or_(
                *(
                    getattr(Lexeme, column).is_distinct_from(value)
                    for column, value in merged.items()
                )
            ),
        ).returning(Lexeme.id, Lexeme.normalized_text, INSERTED)
        rows = await self._session.execute(
            statement,
            [
                {
                    "language_id": self._english_id,
                    "text": draft.text,
                    "normalized_text": draft.normalized_text,
                    "type": draft.lexeme_type,
                    "ipa": draft.ipa,
                    "audio_url": draft.audio_url,
                    "frequency_rank": draft.frequency_rank,
                    "source": LexiconSource.WIKTIONARY,
                }
                for draft in drafts
            ],
        )
        for _, _, inserted in rows:
            self.counts.lexemes_inserted += int(inserted)
            self.counts.lexemes_updated += int(not inserted)
        found = await self._session.execute(
            select(Lexeme.normalized_text, Lexeme.id).where(
                Lexeme.language_id == self._english_id,
                Lexeme.normalized_text.in_([draft.normalized_text for draft in drafts]),
            )
        )
        return dict(found.all())

    async def _upsert_meanings(
        self, drafts: Sequence[LexemeDraft], lexeme_ids: dict[str, int]
    ) -> dict[tuple[int, str | None], int]:
        base = insert(Meaning)
        statement = base.on_conflict_do_update(
            index_elements=[Meaning.lexeme_id, Meaning.source_external_id],
            index_where=Meaning.source_external_id.is_not(None),
            set_={"sense_order": base.excluded.sense_order},
            where=Meaning.sense_order.is_distinct_from(base.excluded.sense_order),
        ).returning(INSERTED)
        rows = await self._session.execute(
            statement,
            [
                {
                    "lexeme_id": lexeme_ids[draft.normalized_text],
                    "part_of_speech": meaning.part_of_speech,
                    "gloss": meaning.gloss,
                    "sense_order": meaning.sense_order,
                    "source": LexiconSource.WIKTIONARY,
                    "source_external_id": meaning.external_id,
                }
                for draft in drafts
                for meaning in draft.meanings
            ],
        )
        for (inserted,) in rows:
            self.counts.meanings_inserted += int(inserted)
            self.counts.meanings_updated += int(not inserted)
        found = await self._session.execute(
            select(Meaning.lexeme_id, Meaning.source_external_id, Meaning.id).where(
                Meaning.lexeme_id.in_(lexeme_ids.values()),
                Meaning.source_external_id.is_not(None),
            )
        )
        return {
            (lexeme_id, external_id): meaning_id for lexeme_id, external_id, meaning_id in found
        }

    async def _insert_translations(
        self,
        drafts: Sequence[LexemeDraft],
        lexeme_ids: dict[str, int],
        meaning_ids: dict[tuple[int, str | None], int],
    ) -> None:
        parameters = [
            {
                "meaning_id": meaning_ids[(lexeme_ids[draft.normalized_text], meaning.external_id)],
                "language_id": self._russian_id,
                "text": text,
                "source": TranslationSource.WIKTIONARY,
            }
            for draft in drafts
            for meaning in draft.meanings
            for text in meaning.translations
        ]
        if not parameters:
            return
        statement = (
            insert(Translation)
            .on_conflict_do_nothing(
                index_elements=[Translation.meaning_id, Translation.language_id, Translation.text]
            )
            .returning(Translation.id)
        )
        rows = (await self._session.execute(statement, parameters)).all()
        self.counts.translations_inserted += len(rows)

    async def _upsert_forms(
        self, drafts: Sequence[LexemeDraft], lexeme_ids: dict[str, int]
    ) -> None:
        parameters = [
            {
                "lexeme_id": lexeme_ids[draft.normalized_text],
                "form_normalized": form.form_normalized,
                "tags": list(form.tags),
            }
            for draft in drafts
            for form in draft.forms
        ]
        if not parameters:
            return
        base = insert(LexemeForm)
        statement = base.on_conflict_do_update(
            index_elements=[LexemeForm.lexeme_id, LexemeForm.form_normalized],
            set_={"tags": base.excluded.tags},
            where=LexemeForm.tags.is_distinct_from(base.excluded.tags),
        ).returning(INSERTED)
        for (inserted,) in await self._session.execute(statement, parameters):
            self.counts.forms_inserted += int(inserted)
            self.counts.forms_updated += int(not inserted)
