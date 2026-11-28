from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.collections.constants import (
    MAX_COLLECTION_DESCRIPTION_LENGTH,
    MAX_COLLECTION_NAME_LENGTH,
)

CollectionName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_COLLECTION_NAME_LENGTH),
]


class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CollectionName
    description: str | None = Field(default=None, max_length=MAX_COLLECTION_DESCRIPTION_LENGTH)


class CollectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CollectionName | None = None
    description: str | None = Field(default=None, max_length=MAX_COLLECTION_DESCRIPTION_LENGTH)


class CollectionItemAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vocabulary_item_id: UUID


class CollectionRef(BaseModel):
    id: UUID
    name: str


class CollectionResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    item_count: int
