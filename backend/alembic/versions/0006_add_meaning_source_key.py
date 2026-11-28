from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_meaning_lexeme_id_source_external_id",
        "meaning",
        ["lexeme_id", "source_external_id"],
        unique=True,
        postgresql_where=sa.text("source_external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_meaning_lexeme_id_source_external_id",
        table_name="meaning",
        postgresql_where=sa.text("source_external_id IS NOT NULL"),
    )
