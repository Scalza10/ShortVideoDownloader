from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration, read from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str
    storage_dir: Path = Path("/data/files")
    temp_dir: Path = Path("/data/tmp")
    retention_hours: float = 12
    max_videos: int = Field(100, ge=1)  # oldest finished videos are deleted beyond this
    workers: int = 2
    max_queue: int = 20
    job_timeout_seconds: int = 180
    cookies_file: Path | None = None
    public_base_url: str | None = None
    web_passcode: str | None = None
    invite_token: str | None = Field(None, min_length=16)  # secret in /join/<token>; empty disables it
    log_level: str = "info"

    @field_validator("invite_token", mode="before")
    @classmethod
    def _empty_invite_token_is_unset(cls, value):
        return value or None
