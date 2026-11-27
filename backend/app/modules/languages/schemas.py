from pydantic import BaseModel, ConfigDict


class LanguageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
