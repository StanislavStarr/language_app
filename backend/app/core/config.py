from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_JWT_SECRET = "local-development-only-jwt-secret-change-me"  # noqa: S105

type AppEnv = Literal["local", "test", "production"]
type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_ignore_empty=True, extra="ignore"
    )

    app_env: AppEnv = "local"
    log_level: LogLevel = "INFO"
    database_url: str = "postgresql+psycopg://vocabulary:vocabulary@localhost:5432/vocabulary"
    jwt_secret: SecretStr = Field(default=SecretStr(DEFAULT_JWT_SECRET), min_length=32)
    access_token_ttl_days: int = Field(default=7, ge=1)
    jobs_run_in_process: bool = True
    jobs_worker_concurrency: int = Field(default=2, ge=1)

    @model_validator(mode="after")
    def require_custom_jwt_secret_in_production(self) -> Self:
        if (
            self.app_env == "production"
            and self.jwt_secret.get_secret_value() == DEFAULT_JWT_SECRET
        ):
            message = "JWT_SECRET must be set in production"
            raise ValueError(message)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
