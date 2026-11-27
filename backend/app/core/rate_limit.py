import math
import time
from collections import deque
from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

from fastapi import Request, status

from app.core.errors import AppError


class RateLimitedError(AppError):
    code = "rate_limited"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many requests",
            {"retry_after_seconds": retry_after_seconds},
            {"Retry-After": str(retry_after_seconds)},
        )


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window: timedelta,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window_seconds = window.total_seconds()
        self._clock = clock
        self._hits: dict[UUID, deque[float]] = {}
        self._last_sweep = clock()

    def acquire(self, key: UUID) -> None:
        now = self._clock()
        self._evict_stale_keys(now)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self._window_seconds:
            hits.popleft()
        if len(hits) >= self._limit:
            raise RateLimitedError(math.ceil(hits[0] + self._window_seconds - now))
        hits.append(now)

    def _evict_stale_keys(self, now: float) -> None:
        if now - self._last_sweep < self._window_seconds:
            return
        self._last_sweep = now
        cutoff = now - self._window_seconds
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]


def get_rate_limiter(request: Request) -> SlidingWindowRateLimiter:
    limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
    return limiter
