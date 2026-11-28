from uuid import UUID

import psycopg
import structlog
from procrastinate.exceptions import ProcrastinateException

from app.modules.enrichment.jobs import enrich_vocabulary_item

logger = structlog.get_logger()


class EnrichmentScheduler:
    async def schedule(self, item_id: UUID) -> None:
        try:
            await enrich_vocabulary_item.defer_async(item_id=str(item_id))
        except (ProcrastinateException, psycopg.Error, OSError):
            logger.error("enrichment_not_scheduled", item_id=str(item_id))
