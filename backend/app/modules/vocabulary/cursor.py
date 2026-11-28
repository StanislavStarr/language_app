import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.vocabulary.exceptions import InvalidCursorError

SEPARATOR = "|"


@dataclass(frozen=True, slots=True)
class VocabularyCursor:
    created_at: datetime
    item_id: UUID

    def encode(self) -> str:
        raw = f"{self.created_at.isoformat()}{SEPARATOR}{self.item_id}"
        return base64.urlsafe_b64encode(raw.encode()).decode()

    @classmethod
    def decode(cls, value: str) -> "VocabularyCursor":
        try:
            raw = base64.urlsafe_b64decode(value.encode()).decode()
            created_at, item_id = raw.split(SEPARATOR)
            parsed = datetime.fromisoformat(created_at)
            if parsed.tzinfo is None:
                raise InvalidCursorError
            return cls(parsed, UUID(item_id))
        except (ValueError, binascii.Error) as error:
            raise InvalidCursorError from error
