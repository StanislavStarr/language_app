from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, string_enum
from app.modules.languages.enums import CefrLevel
from app.modules.users.enums import AnswerLanguage


class User(Base):
    __tablename__ = "user"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    native_language_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("language.id"))
    learning_language_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("language.id"))
    cefr_level: Mapped[CefrLevel] = mapped_column(string_enum(CefrLevel, "cefr_level", 2))
    answer_language: Mapped[AnswerLanguage] = mapped_column(
        string_enum(AnswerLanguage, "answer_language", 16)
    )
    onboarding_completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
