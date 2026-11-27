import asyncio
import importlib.util
import pkgutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import timedelta

import structlog
from procrastinate import App, PsycopgConnector, RetryStrategy
from sqlalchemy.engine import make_url

import app.modules
from app.core.config import Settings, get_settings

STALLED_JOB_THRESHOLD = timedelta(minutes=15)
WORKER_SHUTDOWN_TIMEOUT_SECONDS = 30
DEFAULT_RETRY = RetryStrategy(max_attempts=3, exponential_wait=5)

logger = structlog.get_logger()


def discover_job_modules() -> list[str]:
    return [
        f"app.modules.{module.name}.jobs"
        for module in pkgutil.iter_modules(app.modules.__path__)
        if importlib.util.find_spec(f"app.modules.{module.name}.jobs") is not None
    ]


def create_jobs_app(database_url: str) -> App:
    conninfo = make_url(database_url).set(drivername="postgresql")
    return App(
        connector=PsycopgConnector(conninfo=conninfo.render_as_string(hide_password=False)),
        import_paths=discover_job_modules(),
    )


jobs_app = create_jobs_app(get_settings().database_url)


@jobs_app.task(name="ping_job", retry=DEFAULT_RETRY)
async def ping_job() -> None:
    logger.info("ping_job_executed")


def log_worker_crash(worker: asyncio.Task[None]) -> None:
    if not worker.cancelled() and worker.exception() is not None:
        logger.error("jobs_worker_crashed", error=repr(worker.exception()))


async def requeue_stalled_jobs(jobs: App) -> int:
    stalled = list(
        await jobs.job_manager.get_stalled_jobs(
            nb_seconds=int(STALLED_JOB_THRESHOLD.total_seconds())
        )
    )
    for job in stalled:
        await jobs.job_manager.retry_job(job)
    return len(stalled)


@asynccontextmanager
async def run_jobs(jobs: App, settings: Settings) -> AsyncIterator[None]:
    async with jobs.open_async():
        requeued = await requeue_stalled_jobs(jobs)
        logger.info("stalled_jobs_requeued", count=requeued)
        if not settings.jobs_run_in_process:
            yield
            return
        worker = asyncio.create_task(
            jobs.run_worker_async(
                concurrency=settings.jobs_worker_concurrency,
                install_signal_handlers=False,
                shutdown_graceful_timeout=WORKER_SHUTDOWN_TIMEOUT_SECONDS,
            )
        )
        worker.add_done_callback(log_worker_crash)
        logger.info("jobs_worker_started", concurrency=settings.jobs_worker_concurrency)
        try:
            yield
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
            logger.info("jobs_worker_stopped")
