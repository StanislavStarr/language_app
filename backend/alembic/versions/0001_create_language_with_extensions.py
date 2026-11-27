from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

language_table = sa.table(
    "language",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "language",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_language")),
        sa.UniqueConstraint("code", name=op.f("uq_language_code")),
    )
    op.bulk_insert(
        language_table,
        [{"code": "en", "name": "English"}, {"code": "ru", "name": "Russian"}],
    )


def downgrade() -> None:
    op.drop_table("language")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
