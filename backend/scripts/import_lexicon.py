import argparse
import asyncio
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import batched
from pathlib import Path

from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
from app.modules.languages.repository import LanguageRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from scripts.lexicon_collector import collect_lexemes
from scripts.lexicon_drafts import LexemeDraft, build_drafts
from scripts.lexicon_loader import LexiconBatchLoader, LoadCounts
from scripts.wiktextract import build_ranks, read_lines

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPOSITORY_ROOT / "data/kaikki/raw-wiktextract-data.jsonl.gz"
DEFAULT_TOP_N = 60_000
DEFAULT_PHRASE_TOP_N = 30_000
DEFAULT_BATCH_SIZE = 1_000
PROGRESS_EVERY_LINES = 1_000_000
LEXICON_TABLES = ("lexeme", "lexeme_form", "meaning", "translation")


@dataclass(frozen=True, slots=True)
class Options:
    source: Path
    top_n: int
    phrase_top_n: int
    batch_size: int
    dry_run: bool


def with_progress(lines: Iterable[str]) -> Iterator[str]:
    for number, line in enumerate(lines, start=1):
        if number % PROGRESS_EVERY_LINES == 0:
            sys.stderr.write(f"{number} lines read\n")
        yield line


def positive_integer(raw: str) -> int:
    value = int(raw)
    if value < 1:
        message = "must be a positive integer"
        raise argparse.ArgumentTypeError(message)
    return value


def parse_options(arguments: Sequence[str] | None = None) -> Options:
    parser = argparse.ArgumentParser(description="Import the Wiktionary lexicon into PostgreSQL")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--top-n", type=positive_integer, default=DEFAULT_TOP_N)
    parser.add_argument("--phrase-top-n", type=positive_integer, default=DEFAULT_PHRASE_TOP_N)
    parser.add_argument("--batch-size", type=positive_integer, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true")
    parsed = parser.parse_args(arguments)
    return Options(
        parsed.source, parsed.top_n, parsed.phrase_top_n, parsed.batch_size, parsed.dry_run
    )


def describe_drafts(drafts: Sequence[LexemeDraft]) -> list[str]:
    meanings = [meaning for draft in drafts for meaning in draft.meanings]
    with_translation = sum(1 for meaning in meanings if meaning.translations)
    return [
        f"lexemes: {len(drafts)} (words {sum(d.lexeme_type == 'word' for d in drafts)}, "
        f"phrases {sum(d.lexeme_type == 'phrase' for d in drafts)})",
        f"forms: {sum(len(draft.forms) for draft in drafts)}",
        f"meanings: {len(meanings)}",
        f"translations: {sum(len(meaning.translations) for meaning in meanings)}",
        f"meanings with a Russian translation: {with_translation / max(len(meanings), 1):.1%}",
    ]


def describe_counts(counts: LoadCounts, drafts: Sequence[LexemeDraft]) -> list[str]:
    meanings = sum(len(draft.meanings) for draft in drafts)
    forms = sum(len(draft.forms) for draft in drafts)
    lexemes_changed = counts.lexemes_inserted + counts.lexemes_updated
    meanings_changed = counts.meanings_inserted + counts.meanings_updated
    forms_changed = counts.forms_inserted + counts.forms_updated
    return [
        f"lexemes inserted/updated/unchanged: {counts.lexemes_inserted}/"
        f"{counts.lexemes_updated}/{len(drafts) - lexemes_changed}",
        f"meanings inserted/updated/unchanged: {counts.meanings_inserted}/"
        f"{counts.meanings_updated}/{meanings - meanings_changed}",
        f"translations inserted: {counts.translations_inserted}",
        f"forms inserted/updated/unchanged: {counts.forms_inserted}/"
        f"{counts.forms_updated}/{forms - forms_changed}",
    ]


async def describe_tables(session: AsyncSession) -> list[str]:
    lines: list[str] = []
    for table in LEXICON_TABLES:
        size, rows = (
            await session.execute(
                text(f"SELECT pg_total_relation_size('{table}'), (SELECT count(*) FROM {table})")  # noqa: S608
            )
        ).one()
        lines.append(f"table {table}: {rows} rows, {size / 1024 / 1024:.1f} MB")
    return lines


async def load_all(
    factory: async_sessionmaker[AsyncSession], drafts: Sequence[LexemeDraft], batch_size: int
) -> LoadCounts:
    async with factory() as session:
        languages = LanguageRepository(session)
        english = await languages.find_by_code("en")
        russian = await languages.find_by_code("ru")
    if english is None or russian is None:
        message = "languages en and ru must exist; run `make migrate` first"
        raise SystemExit(message)
    total = LoadCounts()
    processed = 0
    for number, batch in enumerate(batched(drafts, batch_size, strict=False), start=1):
        sys.stderr.write(f"batch {number}: loading {len(batch)} lexemes\n")
        async with factory() as session, session.begin():
            total.add(await LexiconBatchLoader(session, english.id, russian.id).load(batch))
        processed += len(batch)
        sys.stderr.write(f"batch {number} committed, {processed} of {len(drafts)} lexemes done\n")
    return total


async def run(options: Options) -> list[str]:
    ranks = build_ranks(options.top_n)
    collector = collect_lexemes(
        with_progress(read_lines(options.source, None)), ranks, options.phrase_top_n
    )
    drafts = list(build_drafts(collector))
    report = describe_drafts(drafts)
    if collector.invalid_lines:
        report.append(f"skipped invalid lines: {collector.invalid_lines}")
    if options.dry_run:
        return ["dry run, nothing written", *report]
    engine = create_engine(get_settings().database_url)
    factory = create_session_factory(engine)
    try:
        counts = await load_all(factory, drafts, options.batch_size)
        async with factory() as session:
            tables = await describe_tables(session)
    finally:
        await engine.dispose()
    return [*report, *describe_counts(counts, drafts), *tables]


def main() -> None:
    for line in asyncio.run(run(parse_options())):
        sys.stdout.write(f"{line}\n")


if __name__ == "__main__":
    main()
