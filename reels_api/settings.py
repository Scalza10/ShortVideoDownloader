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
    max_favorites: int = Field(200, ge=1)  # starred reels, kept past retention until un-starred
    workers: int = 2
    max_queue: int = 20
    job_timeout_seconds: int = 180
    max_duration_seconds: int = Field(180, ge=1)  # longer videos fail with too_long
    cookies_file: Path | None = None
    public_base_url: str | None = None
    web_passcode: str | None = None
    invite_token: str | None = Field(None, min_length=16)  # secret in /join/<token>; empty disables it
    ios_shortcut_url: str | None = None  # iCloud link to the iPhone share shortcut (shortcut spec 3)
    log_level: str = "info"

    @field_validator("invite_token", "ios_shortcut_url", mode="before")
    @classmethod
    def _empty_is_unset(cls, value):
        return value or None
