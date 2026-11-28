from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.collections.constants import (
    MAX_COLLECTION_DESCRIPTION_LENGTH,
    MAX_COLLECTION_NAME_LENGTH,
)


class Collection(Base):
    __tablename__ = "collection"
    __table_args__ = (
        Index("uq_collection_user_id_lower_name", "user_id", func.lower("name"), unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(MAX_COLLECTION_NAME_LENGTH))
    description: Mapped[str | None] = mapped_column(String(MAX_COLLECTION_DESCRIPTION_LENGTH))
    is_system: Mapped[bool] = mapped_column(server_default=text("false"), default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CollectionItem(Base):
    __tablename__ = "collection_item"

    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), primary_key=True
    )
    user_vocabulary_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_vocabulary_item.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
