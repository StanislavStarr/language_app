from uuid import UUID


class RecordingScheduler:
    def __init__(self) -> None:
        self.scheduled: list[UUID] = []

    async def schedule(self, item_id: UUID) -> None:
        self.scheduled.append(item_id)
