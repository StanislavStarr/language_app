from datetime import timedelta
from uuid import uuid4

import pytest
from app.core.rate_limit import RateLimitedError, SlidingWindowRateLimiter
from fastapi import FastAPI
from httpx import AsyncClient
from tests.factories import bearer, sign_in_new_device


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_acquire_allows_requests_up_to_the_limit() -> None:
    limiter = SlidingWindowRateLimiter(2, timedelta(minutes=1), FakeClock())
    key = uuid4()

    limiter.acquire(key)
    limiter.acquire(key)

    with pytest.raises(RateLimitedError) as limited:
        limiter.acquire(key)
    assert limited.value.headers == {"Retry-After": "60"}


def test_window_slides_so_old_requests_stop_counting() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(2, timedelta(minutes=1), clock)
    key = uuid4()
    limiter.acquire(key)
    clock.now += 30
    limiter.acquire(key)

    clock.now += 31
    limiter.acquire(key)

    with pytest.raises(RateLimitedError) as limited:
        limiter.acquire(key)
    assert limited.value.headers == {"Retry-After": "29"}


def test_keys_are_limited_independently() -> None:
    limiter = SlidingWindowRateLimiter(1, timedelta(minutes=1), FakeClock())

    limiter.acquire(uuid4())
    limiter.acquire(uuid4())


def test_stale_keys_are_evicted_after_the_window() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(1, timedelta(minutes=1), clock)
    for _ in range(3):
        limiter.acquire(uuid4())

    clock.now += 61
    limiter.acquire(uuid4())

    assert len(limiter._hits) == 1


async def test_endpoint_returns_429_with_retry_after_when_limit_is_hit(
    client: AsyncClient, app: FastAPI
) -> None:
    app.state.rate_limiter = SlidingWindowRateLimiter(2, timedelta(minutes=1), FakeClock())
    token = await sign_in_new_device(client)

    await client.get("/api/v1/users/me", headers=bearer(token))
    await client.get("/api/v1/users/me", headers=bearer(token))
    response = await client.get("/api/v1/users/me", headers=bearer(token))

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.headers["Retry-After"] == "60"


async def test_limit_is_per_user(client: AsyncClient, app: FastAPI) -> None:
    app.state.rate_limiter = SlidingWindowRateLimiter(1, timedelta(minutes=1), FakeClock())
    first = await sign_in_new_device(client)
    second = await sign_in_new_device(client)

    await client.get("/api/v1/users/me", headers=bearer(first))
    blocked = await client.get("/api/v1/users/me", headers=bearer(first))
    other_user = await client.get("/api/v1/users/me", headers=bearer(second))

    assert blocked.status_code == 429
    assert other_user.status_code == 200
