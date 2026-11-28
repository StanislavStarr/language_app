from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from app.core.config import get_settings
from sqlalchemy.engine import make_url

from tests.conftest import build_alembic_config

SCRATCH_DATABASE_NAME = "vocabulary_migration_roundtrip"


@pytest.fixture
def scratch_database_url() -> Iterator[str]:
    base_url = make_url(get_settings().database_url)
    admin_dsn = base_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DATABASE_NAME}")
        admin.execute(f"CREATE DATABASE {SCRATCH_DATABASE_NAME}")
        yield base_url.set(database=SCRATCH_DATABASE_NAME).render_as_string(hide_password=False)
        admin.execute(f"DROP DATABASE {SCRATCH_DATABASE_NAME}")


def fetch_all(database_url: str, query: str) -> list[tuple[object, ...]]:
    dsn = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as connection:
        return connection.execute(query).fetchall()


def test_upgrade_seeds_languages_and_downgrade_removes_schema(scratch_database_url: str) -> None:
    config = build_alembic_config(scratch_database_url)

    command.upgrade(config, "head")
    jobs_table = fetch_all(scratch_database_url, "SELECT to_regclass('procrastinate_jobs')")
    user_tables = fetch_all(
        scratch_database_url, "SELECT to_regclass('\"user\"'), to_regclass('auth_identity')"
    )
    usage_table = fetch_all(scratch_database_url, "SELECT to_regclass('daily_usage')")
    lexicon_tables = fetch_all(
        scratch_database_url,
        "SELECT count(*) FROM pg_tables WHERE tablename IN "
        "('lexeme', 'lexeme_form', 'meaning', 'translation', 'meaning_content', "
        "'sense_selection', 'irregular_verb')",
    )
    trigram_index = fetch_all(
        scratch_database_url,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_lexeme_normalized_text_trgm'",
    )
    seeded = fetch_all(scratch_database_url, "SELECT code FROM language ORDER BY id")
    extensions = fetch_all(scratch_database_url, "SELECT extname FROM pg_extension")
    command.downgrade(config, "base")
    table_after_downgrade = fetch_all(scratch_database_url, "SELECT to_regclass('language')")
    extensions_after_downgrade = fetch_all(scratch_database_url, "SELECT extname FROM pg_extension")
    jobs_table_after_downgrade = fetch_all(
        scratch_database_url, "SELECT to_regclass('procrastinate_jobs')"
    )
    user_tables_after_downgrade = fetch_all(
        scratch_database_url, "SELECT to_regclass('\"user\"'), to_regclass('auth_identity')"
    )
    usage_table_after_downgrade = fetch_all(
        scratch_database_url, "SELECT to_regclass('daily_usage')"
    )
    lexicon_tables_after_downgrade = fetch_all(
        scratch_database_url,
        "SELECT count(*) FROM pg_tables WHERE tablename IN ('lexeme', 'meaning', 'translation')",
    )
    command.upgrade(config, "head")

    assert lexicon_tables == [(7,)]
    assert lexicon_tables_after_downgrade == [(0,)]
    assert len(trigram_index) == 1
    assert "gin_trgm_ops" in str(trigram_index[0][0])
    assert usage_table == [("daily_usage",)]
    assert usage_table_after_downgrade == [(None,)]
    assert user_tables == [('"user"', "auth_identity")]
    assert user_tables_after_downgrade == [(None, None)]
    assert jobs_table == [("procrastinate_jobs",)]
    assert jobs_table_after_downgrade == [(None,)]
    assert seeded == [("en",), ("ru",)]
    assert {("vector",), ("pg_trgm",)} <= set(extensions)
    assert table_after_downgrade == [(None,)]
    assert {("vector",), ("pg_trgm",)}.isdisjoint(extensions_after_downgrade)
