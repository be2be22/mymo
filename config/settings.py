"""
Application configuration module.

All settings are loaded from environment variables (or .env file) using
pydantic-settings for validation and type coercion.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object.

    All values are populated from environment variables. A ready-to-edit
    template is provided in ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Telegram ----------
    bot_token: str = Field(..., description="Telegram Bot API token from @BotFather")
    admin_ids: str = Field(
        default="",
        description="Comma-separated Telegram user IDs of administrators",
    )

    # ---------- Channels ----------
    channel_ids: str = Field(
        default="",
        description="Comma-separated channel usernames/IDs for broadcasting",
    )

    # ---------- Database ----------
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/mymoviz.db",
        description="Async SQLAlchemy database URL",
    )

    # ---------- Scraping ----------
    classic_base_url: str = Field(default="https://mymoviz.co")
    modern_base_url: str = Field(default="https://mymoviz.co/_modern/home")

    request_timeout: int = Field(default=30, ge=5, le=120)
    request_max_retries: int = Field(default=3, ge=1, le=10)
    request_backoff_factor: float = Field(default=0.5, ge=0.1, le=5.0)
    rate_limit_delay: float = Field(default=1.5, ge=0.0, le=10.0)
    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    )

    # ---------- Cache ----------
    cache_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    cache_max_size: int = Field(default=1000, ge=10, le=100000)

    # ---------- Scheduler ----------
    check_interval_minutes: int = Field(default=10, ge=1, le=1440)

    # ---------- Logging ----------
    log_level: str = Field(default="INFO")
    log_dir: str = Field(default="logs")

    # ---------- Webhook ----------
    webhook_url: str = Field(default="")
    webhook_port: int = Field(default=8443)
    webhook_path: str = Field(default="/webhook")

    # ---------- Misc ----------
    debug: bool = Field(default=False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @field_validator("admin_ids", "channel_ids")
    @classmethod
    def _strip_commas(cls, v: str) -> str:
        """Strip surrounding whitespace from comma-separated lists."""
        return v.strip()

    @property
    def admin_id_list(self) -> List[int]:
        """Return admin IDs as a list of integers."""
        if not self.admin_ids:
            return []
        result: List[int] = []
        for part in self.admin_ids.split(","):
            part = part.strip()
            if part.isdigit():
                result.append(int(part))
        return result

    @property
    def channel_id_list(self) -> List[str]:
        """Return channel IDs/usernames as a list of strings."""
        if not self.channel_ids:
            return []
        return [c.strip() for c in self.channel_ids.split(",") if c.strip()]

    @property
    def use_webhook(self) -> bool:
        """Whether webhook mode should be used instead of long polling."""
        return bool(self.webhook_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


# Module-level singleton imported across the codebase
settings: Settings = get_settings()


def ensure_data_dir() -> None:
    """Make sure the data/ directory exists for SQLite storage."""
    if settings.database_url.startswith("sqlite"):
        # Extract path from sqlite+aiosqlite:///./data/mymoviz.db
        path_part = settings.database_url.split("///")[-1]
        directory = os.path.dirname(path_part)
        if directory:
            os.makedirs(directory, exist_ok=True)
