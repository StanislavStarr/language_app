import asyncio
from collections.abc import Awaitable, Callable, Sequence

CONCURRENCY = 4


async def run_limited[Item, Result](
    items: Sequence[Item], work: Callable[[Item], Awaitable[Result]]
) -> list[Result]:
    gate = asyncio.Semaphore(CONCURRENCY)

    async def guarded(item: Item) -> Result:
        async with gate:
            return await work(item)

    return list(await asyncio.gather(*(guarded(item) for item in items)))
