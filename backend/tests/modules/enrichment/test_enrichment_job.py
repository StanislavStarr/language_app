from uuid import uuid4

import pytest
from app.integrations.ai.provider import AIUnavailableError, GenerateMeaningContentRequest
from app.integrations.ai.schemas.meaning_content import MeaningContentOutput
from app.modules.enrichment.jobs import (
    ENRICHMENT_MAX_RETRIES,
    enrich_vocabulary_item,
    is_final_attempt,
)
from app.modules.enrichment.runtime import current_runtime, installed_runtime
from app.modules.enrichment.scheduler import EnrichmentScheduler
from httpx import AsyncClient
from procrastinate import App
from procrastinate.exceptions import ConnectorException
from procrastinate.testing import InMemoryConnector
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.modules.enrichment.enrichment_setup import (
    card,
    fake_ai,
    meaning_without_translation,
    runtime_over,
    saved_item,
)
from tests.modules.vocabulary.vocabulary_api import new_meaning_id


def test_only_the_last_attempt_may_finish_with_a_degraded_card() -> None:
    attempts = range(ENRICHMENT_MAX_RETRIES + 1)

    assert [is_final_attempt(made) for made in attempts] == [False, False, False, True]


async def test_scheduler_queues_the_job_with_the_item_id(in_memory_jobs: App) -> None:
    connector = in_memory_jobs.connector
    assert isinstance(connector, InMemoryConnector)
    item_id = uuid4()

    await EnrichmentScheduler().schedule(item_id)

    [job] = connector.jobs.values()
    assert job["task_name"] == "enrich_vocabulary_item"
    assert job["args"] == {"item_id": str(item_id)}
    assert job["queue_name"] == "enrichment"


async def test_a_queue_outage_is_logged_and_does_not_raise(monkeypatch: MonkeyPatch) -> None:
    async def broken(**_kwargs: object) -> int:
        raise ConnectorException("queue is down")

    monkeypatch.setattr(enrich_vocabulary_item, "defer_async", broken)

    with capture_logs() as logs:
        await EnrichmentScheduler().schedule(uuid4())

    assert [entry["event"] for entry in logs] == ["enrichment_not_scheduled"]


async def test_worker_prepares_the_card(
    client: AsyncClient, db_session: AsyncSession, in_memory_jobs: App
) -> None:
    headers, item_id = await saved_item(client, await meaning_without_translation(db_session))

    with installed_runtime(runtime_over(db_session, fake_ai())):
        await EnrichmentScheduler().schedule(item_id)
        await in_memory_jobs.run_worker_async(wait=False)

    connector = in_memory_jobs.connector
    assert isinstance(connector, InMemoryConnector)
    assert [job["status"] for job in connector.jobs.values()] == ["succeeded"]
    assert (await card(client, headers, item_id))["enrichment_status"] == "ready"


def test_the_runtime_must_be_installed_before_a_job_runs() -> None:
    with pytest.raises(RuntimeError):
        current_runtime()


async def test_outage_reschedules_the_job_and_the_last_attempt_settles_the_card(
    client: AsyncClient, db_session: AsyncSession, in_memory_jobs: App
) -> None:
    headers, item_id = await saved_item(client, await meaning_without_translation(db_session))
    connector = in_memory_jobs.connector
    assert isinstance(connector, InMemoryConnector)
    down = FakeAIProvider(error=AIUnavailableError("down"))

    with installed_runtime(runtime_over(db_session, down)):
        await EnrichmentScheduler().schedule(item_id)
        await in_memory_jobs.run_worker_async(wait=False)
        [job] = connector.jobs.values()
        first = (job["status"], job["attempts"])
        pending = (await card(client, headers, item_id))["enrichment_status"]
        job["attempts"] = ENRICHMENT_MAX_RETRIES
        job["scheduled_at"] = None
        job["status"] = "todo"
        await in_memory_jobs.run_worker_async(wait=False)

    assert first == ("todo", 1)
    assert pending == "enriching"
    assert (await card(client, headers, item_id))["enrichment_status"] == "failed"


async def test_unexpected_failure_on_the_last_attempt_does_not_leave_the_card_stuck(
    client: AsyncClient, db_session: AsyncSession, in_memory_jobs: App
) -> None:
    headers, item_id = await saved_item(client, await new_meaning_id(db_session, "bank"))
    connector = in_memory_jobs.connector
    assert isinstance(connector, InMemoryConnector)

    def explode(_request: GenerateMeaningContentRequest) -> MeaningContentOutput:
        raise RuntimeError("boom")

    with installed_runtime(runtime_over(db_session, fake_ai(content=explode))):
        await EnrichmentScheduler().schedule(item_id)
        [job] = connector.jobs.values()
        job["attempts"] = ENRICHMENT_MAX_RETRIES
        await in_memory_jobs.run_worker_async(wait=False)

    assert [job["status"] for job in connector.jobs.values()] == ["failed"]
    assert (await card(client, headers, item_id))["enrichment_status"] == "partial"
