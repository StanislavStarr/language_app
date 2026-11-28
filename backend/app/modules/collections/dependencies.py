from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.collections.repository import CollectionRepository
from app.modules.collections.service import CollectionService
from app.modules.vocabulary.access import build_vocabulary_access


def get_collection_service(session: SessionDep) -> CollectionService:
    return CollectionService(
        session, CollectionRepository(session), build_vocabulary_access(session)
    )


type CollectionServiceDep = Annotated[CollectionService, Depends(get_collection_service)]
