from typing import Annotated

from fastapi import Depends

from app.core.database import SessionDep
from app.modules.collections.dependencies import CollectionServiceDep
from app.modules.enrichment.scheduler import EnrichmentScheduler
from app.modules.lexicon.catalog import build_meaning_catalog
from app.modules.vocabulary.repository import VocabularyRepository
from app.modules.vocabulary.service import VocabularyService


def get_enrichment_scheduler() -> EnrichmentScheduler:
    return EnrichmentScheduler()


def get_vocabulary_service(
    session: SessionDep,
    collections: CollectionServiceDep,
    scheduler: Annotated[EnrichmentScheduler, Depends(get_enrichment_scheduler)],
) -> VocabularyService:
    return VocabularyService(
        session,
        VocabularyRepository(session),
        collections,
        build_meaning_catalog(session),
        scheduler,
    )


type VocabularyServiceDep = Annotated[VocabularyService, Depends(get_vocabulary_service)]
