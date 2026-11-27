from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_usage",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "ai_lookup",
                "book_question",
                "book_upload",
                name="usage_kind",
                native_enum=False,
                length=16,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.CheckConstraint("count >= 0", name=op.f("ck_daily_usage_count_non_negative")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_daily_usage_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "day", "kind", name=op.f("pk_daily_usage")),
    )


def downgrade() -> None:
    op.drop_table("daily_usage")
