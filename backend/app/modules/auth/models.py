from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, string_enum
from app.modules.auth.enums import AuthProvider


class AuthIdentity(Base):
    __tablename__ = "auth_identity"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    provider: Mapped[AuthProvider] = mapped_column(string_enum(AuthProvider, "auth_provider", 16))
    external_id: Mapped[str]
    secret_hash: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
