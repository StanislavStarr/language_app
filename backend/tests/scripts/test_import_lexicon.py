import json
from pathlib import Path

import pytest
from app.modules.languages.repository import LanguageRepository
from app.modules.lexicon.enums import LexemeType, LexiconSource, PartOfSpeech
from app.modules.lexicon.models import Lexeme, LexemeForm, Meaning, Translation
from scripts.import_lexicon import Options, parse_options, run
from scripts.lexicon_drafts import FormDraft, LexemeDraft, MeaningDraft
from scripts.lexicon_loader import LexiconBatchLoader
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession


def meaning(gloss: str, order: int, *translations: str) -> MeaningDraft:
    return MeaningDraft(PartOfSpeech.NOUN, gloss, order, f"id-{gloss}", translations)


def draft(
    text: str = "bank",
    meanings: tuple[MeaningDraft, ...] | None = None,
    forms: tuple[FormDraft, ...] = (FormDraft("banks", ("plural",)),),
    ipa: str | None = "/bank/",
) -> LexemeDraft:
    return LexemeDraft(
        text=text,
        normalized_text=text.lower(),
        lexeme_type=LexemeType.WORD,
        ipa=ipa,
        audio_url=None,
        frequency_rank=700,
        meanings=meanings
        if meanings is not None
        else (meaning("An institution.", 1, "банк", "касса"), meaning("A river bank.", 2)),
        forms=forms,
    )


async def loader(session: AsyncSession) -> LexiconBatchLoader:
    languages = LanguageRepository(session)
    english = await languages.find_by_code("en")
    russian = await languages.find_by_code("ru")
    assert english is not None
    assert russian is not None
    return LexiconBatchLoader(session, english.id, russian.id)


async def count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def meaning_ids(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(select(Meaning.source_external_id, Meaning.id))
    return {external_id: meaning_id for external_id, meaning_id in rows if external_id is not None}


async def row_versions(session: AsyncSession) -> list[str]:
    rows = await session.execute(
        text(
            "SELECT xmin::text FROM lexeme UNION ALL SELECT xmin::text FROM meaning "
            "UNION ALL SELECT xmin::text FROM lexeme_form ORDER BY 1"
        )
    )
    return [version for (version,) in rows]


async def test_load_writes_lexemes_meanings_translations_and_forms(
    db_session: AsyncSession,
) -> None:
    counts = await (await loader(db_session)).load([draft()])

    assert (counts.lexemes_inserted, counts.meanings_inserted) == (1, 2)
    assert (counts.translations_inserted, counts.forms_inserted) == (2, 1)
    assert await count(db_session, Translation) == 2
    lexeme = (await db_session.scalars(select(Lexeme))).one()
    assert (lexeme.text, lexeme.ipa, lexeme.source) == ("bank", "/bank/", LexiconSource.WIKTIONARY)


async def test_loading_the_same_data_twice_changes_nothing(db_session: AsyncSession) -> None:
    await (await loader(db_session)).load([draft()])
    ids_before = await meaning_ids(db_session)
    versions_before = await row_versions(db_session)

    counts = await (await loader(db_session)).load([draft()])

    assert (counts.lexemes_inserted, counts.meanings_inserted) == (0, 0)
    assert (counts.translations_inserted, counts.forms_inserted) == (0, 0)
    assert (counts.lexemes_updated, counts.meanings_updated, counts.forms_updated) == (0, 0, 0)
    assert await meaning_ids(db_session) == ids_before
    assert await row_versions(db_session) == versions_before
    assert [
        await count(db_session, model) for model in (Lexeme, Meaning, Translation, LexemeForm)
    ] == [1, 2, 2, 1]


async def test_reordered_meanings_keep_their_ids(db_session: AsyncSession) -> None:
    await (await loader(db_session)).load([draft()])
    ids_before = await meaning_ids(db_session)
    reordered = draft(
        meanings=(meaning("A river bank.", 1), meaning("An institution.", 2, "банк", "касса"))
    )

    counts = await (await loader(db_session)).load([reordered])

    assert (counts.meanings_updated, counts.lexemes_updated) == (2, 0)
    assert await meaning_ids(db_session) == ids_before
    rows = await db_session.execute(select(Meaning.gloss, Meaning.sense_order))
    orders = dict(rows.all())
    assert orders == {"A river bank.": 1, "An institution.": 2}


async def test_new_translations_and_forms_are_added_on_reload(db_session: AsyncSession) -> None:
    await (await loader(db_session)).load([draft()])
    richer = draft(
        meanings=(
            meaning("An institution.", 1, "банк", "касса", "ссуда"),
            meaning("A river bank.", 2),
        ),
        forms=(FormDraft("banks", ("plural",)), FormDraft("banked", ("past",))),
    )

    counts = await (await loader(db_session)).load([richer])

    assert (counts.translations_inserted, counts.forms_inserted) == (1, 1)


async def test_missing_pronunciation_does_not_erase_existing_data(db_session: AsyncSession) -> None:
    await (await loader(db_session)).load([draft(ipa="/bank/")])

    await (await loader(db_session)).load([draft(ipa=None)])

    assert (await db_session.scalars(select(Lexeme.ipa))).one() == "/bank/"


async def test_lexeme_from_another_source_is_taken_over_by_wiktionary(
    db_session: AsyncSession,
) -> None:
    session_loader = await loader(db_session)
    db_session.add(
        Lexeme(
            language_id=session_loader._english_id,
            text="bank",
            normalized_text="bank",
            type=LexemeType.WORD,
            source=LexiconSource.AI,
        )
    )
    await db_session.flush()

    counts = await session_loader.load([draft()])

    assert counts.lexemes_updated == 1
    assert (await db_session.scalars(select(Lexeme.source))).one() == LexiconSource.WIKTIONARY


async def test_meanings_without_a_source_key_are_never_touched(db_session: AsyncSession) -> None:
    session_loader = await loader(db_session)
    await session_loader.load([draft()])
    lexeme = (await db_session.scalars(select(Lexeme))).one()
    manual = Meaning(
        lexeme_id=lexeme.id,
        part_of_speech=PartOfSpeech.NOUN,
        gloss="Added by AI.",
        sense_order=99,
        source=LexiconSource.AI,
    )
    db_session.add(manual)
    await db_session.flush()

    await (await loader(db_session)).load([draft(meanings=(meaning("An institution.", 1),))])

    await db_session.refresh(manual)
    assert (manual.gloss, manual.sense_order, manual.source) == (
        "Added by AI.",
        99,
        LexiconSource.AI,
    )


async def test_batches_can_be_loaded_separately(db_session: AsyncSession) -> None:
    await (await loader(db_session)).load([draft("bank")])
    await (await loader(db_session)).load([draft("house", forms=())])

    assert await count(db_session, Lexeme) == 2


def test_options_must_be_positive() -> None:
    with pytest.raises(SystemExit):
        parse_options(["--batch-size", "0"])


def test_default_options() -> None:
    options = parse_options([])

    assert (options.top_n, options.phrase_top_n, options.batch_size) == (60_000, 30_000, 1_000)
    assert not options.dry_run


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    path = tmp_path / "dump.jsonl"
    entry = {
        "word": "house",
        "lang_code": "en",
        "pos": "noun",
        "senses": [{"glosses": ["A building."]}],
        "translations": [{"lang_code": "ru", "sense": "building", "word": "дом"}],
    }
    path.write_text(json.dumps(entry) + "\n")
    return path


async def test_dry_run_reports_counts_without_touching_the_database(source_file: Path) -> None:
    options = Options(source_file, 60_000, 30_000, 1_000, dry_run=True)

    report = await run(options)

    assert report[0] == "dry run, nothing written"
    assert "lexemes: 1 (words 1, phrases 0)" in report
    assert "meanings with a Russian translation: 100.0%" in report
