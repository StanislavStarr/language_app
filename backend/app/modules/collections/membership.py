from uuid import UUID

from sqlalchemy import Select, select

from app.modules.collections.models import CollectionItem


def item_ids_in_collection(collection_id: UUID) -> Select[UUID]:
    return select(CollectionItem.user_vocabulary_item_id).where(
        CollectionItem.collection_id == collection_id
    )
