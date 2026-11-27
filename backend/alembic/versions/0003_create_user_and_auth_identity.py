from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("native_language_id", sa.BigInteger(), nullable=False),
        sa.Column("learning_language_id", sa.BigInteger(), nullable=False),
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
                length=2,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "answer_language",
            sa.Enum(
                "en_simple",
                "ru",
                name="answer_language",
                native_enum=False,
                length=16,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["learning_language_id"],
            ["language.id"],
            name=op.f("fk_user_learning_language_id_language"),
        ),
        sa.ForeignKeyConstraint(
            ["native_language_id"],
            ["language.id"],
            name=op.f("fk_user_native_language_id_language"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
    )
    op.create_table(
        "auth_identity",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum(
                "device", name="auth_provider", native_enum=False, length=16, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_auth_identity_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_identity")),
        sa.UniqueConstraint("provider", "external_id", name=op.f("uq_auth_identity_provider")),
    )
    op.create_index(op.f("ix_auth_identity_user_id"), "auth_identity", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_identity_user_id"), table_name="auth_identity")
    op.drop_table("auth_identity")
    op.drop_table("user")
