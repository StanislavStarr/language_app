from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.usage.enums import UsageKind


class DailyUsage(Base):
    __tablename__ = "daily_usage"
    __table_args__ = (CheckConstraint("count >= 0", name="count_non_negative"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(primary_key=True)
    kind: Mapped[UsageKind] = mapped_column(
        Enum(
            UsageKind,
            name="usage_kind",
            native_enum=False,
            length=16,
            create_constraint=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        primary_key=True,
    )
    count: Mapped[int]
