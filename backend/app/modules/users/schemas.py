from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.users.enums import AnswerLanguage, CefrLevel


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cefr_level: CefrLevel | None = None
    answer_language: AnswerLanguage | None = None
    complete_onboarding: bool = False


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    native_language_id: int
    learning_language_id: int
    cefr_level: CefrLevel
    answer_language: AnswerLanguage
    onboarding_completed_at: datetime | None
