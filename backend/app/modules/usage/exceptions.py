from datetime import datetime

from fastapi import status

from app.core.errors import AppError
from app.modules.usage.enums import UsageKind


class UsageLimitExceededError(AppError):
    code = "usage_limit_exceeded"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, kind: UsageKind, limit: int, resets_at: datetime) -> None:
        super().__init__(
            "Daily usage limit exceeded",
            {"kind": kind.value, "limit": limit, "resets_at": resets_at.isoformat()},
        )
