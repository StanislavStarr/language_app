from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.constants import DEVICE_SECRET_MAX_LENGTH, DEVICE_SECRET_MIN_LENGTH


class DeviceLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    install_id: UUID
    device_secret: str = Field(
        min_length=DEVICE_SECRET_MIN_LENGTH, max_length=DEVICE_SECRET_MAX_LENGTH
    )


class TokenResponse(BaseModel):
    access_token: str
