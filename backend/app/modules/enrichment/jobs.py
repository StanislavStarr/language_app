from uuid import UUID

import structlog
from procrastinate import JobContext, RetryStrategy

from app.core.jobs import jobs_app
from app.modules.enrichment.runtime import EnrichmentRuntime, current_runtime
from app.modules.enrichment.service import build_enrichment_service

ENRICHMENT_MAX_RETRIES = 3
ENRICHMENT_RETRY = RetryStrategy(max_attempts=ENRICHMENT_MAX_RETRIES, exponential_wait=5)

logger = structlog.get_logger()


def is_final_attempt(attempts_made: int) -> bool:
    return attempts_made >= ENRICHMENT_MAX_RETRIES


async def abandon_item(runtime: EnrichmentRuntime, item_id: UUID) -> None:
    try:
        async with runtime.session_factory() as session:
            await build_enrichment_service(session, runtime.ai).abandon(item_id)
    except Exception:
        logger.exception("enrichment_abandon_failed", item_id=str(item_id))


@jobs_app.task(
    name="enrich_vocabulary_item", queue="enrichment", retry=ENRICHMENT_RETRY, pass_context=True
)
async def enrich_vocabulary_item(context: JobContext, item_id: str) -> None:
    runtime = current_runtime()
    final_attempt = is_final_attempt(context.job.attempts)
    try:
        async with runtime.session_factory() as session:
            service = build_enrichment_service(session, runtime.ai)
            await service.enrich_item(UUID(item_id), final_attempt=final_attempt)
    except Exception:
        if final_attempt:
            await abandon_item(runtime, UUID(item_id))
        raise
