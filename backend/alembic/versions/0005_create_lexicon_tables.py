from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lexeme",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("language_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("normalized_text", sa.String(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "word",
                "phrase",
                name="lexeme_type",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("ipa", sa.String(), nullable=True),
        sa.Column("audio_url", sa.String(), nullable=True),
        sa.Column("frequency_rank", sa.Integer(), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "wiktionary",
                "free_dictionary",
                "ai",
                name="lexicon_source",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["language_id"], ["language.id"], name=op.f("fk_lexeme_language_id_language")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lexeme")),
        sa.UniqueConstraint("language_id", "normalized_text", name=op.f("uq_lexeme_language_id")),
    )
    op.create_index(
        "ix_lexeme_normalized_text_trgm",
        "lexeme",
        ["normalized_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"normalized_text": "gin_trgm_ops"},
    )
    op.create_table(
        "irregular_verb",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("base_lexeme_id", sa.BigInteger(), nullable=False),
        sa.Column("past_simple", sa.String(), nullable=False),
        sa.Column("past_participle", sa.String(), nullable=False),
        sa.Column("past_simple_audio_url", sa.String(), nullable=True),
        sa.Column("past_participle_audio_url", sa.String(), nullable=True),
        sa.Column("translation", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["base_lexeme_id"],
            ["lexeme.id"],
            name=op.f("fk_irregular_verb_base_lexeme_id_lexeme"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_irregular_verb")),
        sa.UniqueConstraint("base_lexeme_id", name=op.f("uq_irregular_verb_base_lexeme_id")),
    )
    op.create_table(
        "lexeme_form",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("lexeme_id", sa.BigInteger(), nullable=False),
        sa.Column("form_normalized", sa.String(), nullable=False),
        sa.Column("tags", sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lexeme_id"],
            ["lexeme.id"],
            name=op.f("fk_lexeme_form_lexeme_id_lexeme"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lexeme_form")),
        sa.UniqueConstraint("lexeme_id", "form_normalized", name=op.f("uq_lexeme_form_lexeme_id")),
    )
    op.create_index(
        op.f("ix_lexeme_form_form_normalized"), "lexeme_form", ["form_normalized"], unique=False
    )
    op.create_table(
        "meaning",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("lexeme_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "part_of_speech",
            sa.Enum(
                "noun",
                "verb",
                "adj",
                "adv",
                "pron",
                "prep",
                "conj",
                "det",
                "intj",
                "num",
                "particle",
                "phrase",
                "other",
                name="part_of_speech",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("gloss", sa.String(), nullable=False),
        sa.Column("sense_order", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "wiktionary",
                "free_dictionary",
                "ai",
                name="lexicon_source",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("source_external_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lexeme_id"],
            ["lexeme.id"],
            name=op.f("fk_meaning_lexeme_id_lexeme"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meaning")),
    )
    op.create_index(
        "ix_meaning_lexeme_id_sense_order", "meaning", ["lexeme_id", "sense_order"], unique=False
    )
    op.create_table(
        "meaning_content",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("meaning_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "cefr_level",
            sa.Enum(
                "A1",
                "A2",
                "B1",
                "B2",
                "C1",
                "C2",
                name="cefr_level",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("definition", sa.String(), nullable=True),
        sa.Column("example", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "ready",
                "failed",
                name="meaning_content_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["meaning_id"],
            ["meaning.id"],
            name=op.f("fk_meaning_content_meaning_id_meaning"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meaning_content")),
        sa.UniqueConstraint(
            "meaning_id", "cefr_level", "prompt_version", name=op.f("uq_meaning_content_meaning_id")
        ),
    )
    op.create_table(
        "sense_selection",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("lexeme_id", sa.BigInteger(), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("selected_meaning_id", sa.BigInteger(), nullable=True),
        sa.Column("contextual_translation", sa.String(), nullable=True),
        sa.Column("confidence", sa.Double(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name=op.f("ck_sense_selection_confidence_range")
        ),
        sa.ForeignKeyConstraint(
            ["lexeme_id"],
            ["lexeme.id"],
            name=op.f("fk_sense_selection_lexeme_id_lexeme"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["selected_meaning_id"],
            ["meaning.id"],
            name=op.f("fk_sense_selection_selected_meaning_id_meaning"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sense_selection")),
        sa.UniqueConstraint(
            "lexeme_id", "context_hash", "prompt_version", name=op.f("uq_sense_selection_lexeme_id")
        ),
    )
    op.create_index(
        op.f("ix_sense_selection_selected_meaning_id"),
        "sense_selection",
        ["selected_meaning_id"],
        unique=False,
    )
    op.create_table(
        "translation",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("meaning_id", sa.BigInteger(), nullable=False),
        sa.Column("language_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "wiktionary",
                "ai",
                name="translation_source",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["language_id"], ["language.id"], name=op.f("fk_translation_language_id_language")
        ),
        sa.ForeignKeyConstraint(
            ["meaning_id"],
            ["meaning.id"],
            name=op.f("fk_translation_meaning_id_meaning"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_translation")),
        sa.UniqueConstraint(
            "meaning_id", "language_id", "text", name=op.f("uq_translation_meaning_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("translation")
    op.drop_index(op.f("ix_sense_selection_selected_meaning_id"), table_name="sense_selection")
    op.drop_table("sense_selection")
    op.drop_table("meaning_content")
    op.drop_index("ix_meaning_lexeme_id_sense_order", table_name="meaning")
    op.drop_table("meaning")
    op.drop_index(op.f("ix_lexeme_form_form_normalized"), table_name="lexeme_form")
    op.drop_table("lexeme_form")
    op.drop_table("irregular_verb")
    op.drop_index(
        "ix_lexeme_normalized_text_trgm",
        table_name="lexeme",
        postgresql_using="gin",
        postgresql_ops={"normalized_text": "gin_trgm_ops"},
    )
    op.drop_table("lexeme")
