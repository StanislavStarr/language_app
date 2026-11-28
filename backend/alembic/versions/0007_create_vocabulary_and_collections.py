from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            ["user_id"], ["user.id"], name=op.f("fk_collection_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection")),
    )
    op.create_index(
        "uq_collection_user_id_lower_name",
        "collection",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )
    op.create_table(
        "user_vocabulary_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("meaning_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "manual",
                "book",
                name="source_type",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("book_id", sa.Uuid(), nullable=True),
        sa.Column("paragraph_id", sa.BigInteger(), nullable=True),
        sa.Column("source_context", sa.String(length=500), nullable=True),
        sa.Column("context_translation", sa.String(length=200), nullable=True),
        sa.Column("personal_note", sa.String(length=500), nullable=True),
        sa.Column("meaning_content_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "enrichment_status",
            sa.Enum(
                "pending",
                "enriching",
                "ready",
                "partial",
                "failed",
                name="enrichment_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("study_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_studied_at", sa.DateTime(timezone=True), nullable=True),
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
            ["meaning_content_id"],
            ["meaning_content.id"],
            name=op.f("fk_user_vocabulary_item_meaning_content_id_meaning_content"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["meaning_id"], ["meaning.id"], name=op.f("fk_user_vocabulary_item_meaning_id_meaning")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_user_vocabulary_item_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_vocabulary_item")),
        sa.UniqueConstraint("user_id", "meaning_id", name=op.f("uq_user_vocabulary_item_user_id")),
    )
    op.create_index(
        "ix_user_vocabulary_item_user_id_created_at_id",
        "user_vocabulary_item",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "collection_item",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("user_vocabulary_item_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collection.id"],
            name=op.f("fk_collection_item_collection_id_collection"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_vocabulary_item_id"],
            ["user_vocabulary_item.id"],
            name=op.f("fk_collection_item_user_vocabulary_item_id_user_vocabulary_item"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "collection_id", "user_vocabulary_item_id", name=op.f("pk_collection_item")
        ),
    )
    op.create_index(
        op.f("ix_collection_item_user_vocabulary_item_id"),
        "collection_item",
        ["user_vocabulary_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_collection_item_user_vocabulary_item_id"), table_name="collection_item")
    op.drop_table("collection_item")
    op.drop_index(
        "ix_user_vocabulary_item_user_id_created_at_id", table_name="user_vocabulary_item"
    )
    op.drop_table("user_vocabulary_item")
    op.drop_index("uq_collection_user_id_lower_name", table_name="collection")
    op.drop_table("collection")
