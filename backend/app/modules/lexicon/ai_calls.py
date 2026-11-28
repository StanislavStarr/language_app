from collections.abc import Awaitable, Callable

import structlog

from app.integrations.ai.provider import AIError, AIInvalidOutputError, AIResult

logger = structlog.get_logger()
ATTEMPTS = 2


async def call_with_one_retry[Output](
    feature: str, call: Callable[[], Awaitable[AIResult[Output]]]
) -> AIResult[Output] | None:
    for _ in range(ATTEMPTS):
        try:
            return await call()
        except AIInvalidOutputError:
            continue
        except AIError:
            break
    logger.warning("ai_degraded", feature=feature)
    return None
