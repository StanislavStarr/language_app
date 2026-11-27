from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.users.enums import AnswerLanguage, CefrLevel


class User(Base):
    __tablename__ = "user"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    native_language_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("language.id"))
    learning_language_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("language.id"))
    cefr_level: Mapped[CefrLevel] = mapped_column(
        Enum(
            CefrLevel,
            name="cefr_level",
            native_enum=False,
            length=2,
            create_constraint=True,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    answer_language: Mapped[AnswerLanguage] = mapped_column(
        Enum(
            AnswerLanguage,
            name="answer_language",
            native_enum=False,
            length=16,
            create_constraint=True,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    onboarding_completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
