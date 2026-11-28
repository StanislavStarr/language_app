from uuid import UUID

from app.integrations.ai.provider import AIProvider
from app.modules.usage.enums import UsageKind
from app.modules.usage.exceptions import UsageLimitExceededError
from app.modules.usage.service import UsageService


class AiAccess:
    def __init__(self, provider: AIProvider | None, usage: UsageService, user_id: UUID) -> None:
        self._provider = provider
        self._usage = usage
        self._user_id = user_id
        self._granted: bool | None = None
        self.limit_exceeded = False

    async def provider(self) -> AIProvider | None:
        if self._provider is None:
            return None
        if self._granted is None:
            try:
                await self._usage.consume(self._user_id, UsageKind.AI_LOOKUP)
                self._granted = True
            except UsageLimitExceededError:
                self._granted = False
                self.limit_exceeded = True
        return self._provider if self._granted else None
