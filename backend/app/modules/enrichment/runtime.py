from collections.abc import Callable, Iterator
from contextlib import AbstractAsyncContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.ai.provider import AIProvider


@dataclass(frozen=True, slots=True)
class EnrichmentRuntime:
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]]
    ai: AIProvider | None


_installed: ContextVar[EnrichmentRuntime | None] = ContextVar("enrichment_runtime", default=None)


@contextmanager
def installed_runtime(runtime: EnrichmentRuntime) -> Iterator[None]:
    token = _installed.set(runtime)
    try:
        yield
    finally:
        _installed.reset(token)


def current_runtime() -> EnrichmentRuntime:
    runtime = _installed.get()
    if runtime is None:
        message = "enrichment runtime is not installed"
        raise RuntimeError(message)
    return runtime
