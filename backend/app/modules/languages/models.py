from datetime import datetime

from sqlalchemy import BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Language(Base):
    __tablename__ = "language"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
