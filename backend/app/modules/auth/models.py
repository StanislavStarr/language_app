from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.auth.enums import AuthProvider


class AuthIdentity(Base):
    __tablename__ = "auth_identity"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    provider: Mapped[AuthProvider] = mapped_column(
        Enum(
            AuthProvider,
            name="auth_provider",
            native_enum=False,
            length=16,
            create_constraint=True,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    external_id: Mapped[str]
    secret_hash: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
