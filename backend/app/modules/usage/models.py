from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, string_enum
from app.modules.usage.enums import UsageKind


class DailyUsage(Base):
    __tablename__ = "daily_usage"
    __table_args__ = (CheckConstraint("count >= 0", name="count_non_negative"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(primary_key=True)
    kind: Mapped[UsageKind] = mapped_column(
        string_enum(UsageKind, "usage_kind", 16), primary_key=True
    )
    count: Mapped[int]
