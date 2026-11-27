from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

type AppEnv = Literal["local", "test", "production"]
type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_env: AppEnv = "local"
    log_level: LogLevel = "INFO"
    database_url: str = "postgresql+psycopg://vocabulary:vocabulary@localhost:5432/vocabulary"
    jobs_run_in_process: bool = True
    jobs_worker_concurrency: int = Field(default=2, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
