import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.jobs import STALLED_JOB_THRESHOLD, ping_job, requeue_stalled_jobs, run_jobs
from procrastinate import App
from procrastinate.testing import InMemoryConnector
from structlog.testing import capture_logs


async def wait_for_status(connector: InMemoryConnector, status: str) -> None:
    async with asyncio.timeout(5):
        while not any(job["status"] == status for job in connector.jobs.values()):  # noqa: ASYNC110
            await asyncio.sleep(0.01)


async def test_deferred_ping_job_is_executed_by_worker(in_memory_jobs: App) -> None:
    connector = in_memory_jobs.connector
    assert isinstance(connector, InMemoryConnector)

    with capture_logs() as logs:
        await ping_job.defer_async()
        await in_memory_jobs.run_worker_async(wait=False)

    assert [job["status"] for job in connector.jobs.values()] == ["succeeded"]
    assert {"event": "ping_job_executed", "log_level": "info"} in logs


async def test_requeue_stalled_jobs_returns_only_old_doing_jobs(in_memory_jobs: App) -> None:
    connector = in_memory_jobs.connector
    assert isinstance(connector, InMemoryConnector)
    stalled_id = await ping_job.defer_async()
    fresh_id = await ping_job.defer_async()
    now = datetime.now(UTC)
    connector.jobs[stalled_id]["status"] = "doing"
    connector.events[stalled_id].append(
        {"type": "started", "at": now - STALLED_JOB_THRESHOLD - timedelta(minutes=1)}
    )
    connector.jobs[fresh_id]["status"] = "doing"
    connector.events[fresh_id].append({"type": "started", "at": now})

    requeued = await requeue_stalled_jobs(in_memory_jobs)

    assert requeued == 1
    assert connector.jobs[stalled_id]["status"] == "todo"
    assert connector.jobs[fresh_id]["status"] == "doing"


async def test_run_jobs_executes_deferred_job_in_process(in_memory_jobs: App) -> None:
    connector = in_memory_jobs.connector
    assert isinstance(connector, InMemoryConnector)
    settings = Settings(jobs_run_in_process=True)

    async with run_jobs(in_memory_jobs, settings):
        await ping_job.defer_async()
        await wait_for_status(connector, "succeeded")


async def test_run_jobs_without_worker_leaves_jobs_queued(in_memory_jobs: App) -> None:
    connector = in_memory_jobs.connector
    assert isinstance(connector, InMemoryConnector)
    settings = Settings(jobs_run_in_process=False)

    async with run_jobs(in_memory_jobs, settings):
        await ping_job.defer_async()
        await asyncio.sleep(0.2)

    assert [job["status"] for job in connector.jobs.values()] == ["todo"]


async def test_run_jobs_lets_running_job_finish_on_shutdown(in_memory_jobs: App) -> None:
    connector = in_memory_jobs.connector
    assert isinstance(connector, InMemoryConnector)
    started = asyncio.Event()
    release = asyncio.Event()

    @in_memory_jobs.task(name="blocking_job")
    async def blocking_job() -> None:
        started.set()
        await release.wait()

    async with run_jobs(in_memory_jobs, Settings(jobs_run_in_process=True)):
        await blocking_job.defer_async()
        await started.wait()
        asyncio.get_running_loop().call_later(0.1, release.set)

    assert [job["status"] for job in connector.jobs.values()] == ["succeeded"]
