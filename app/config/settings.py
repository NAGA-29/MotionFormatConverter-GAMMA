"""Environment-driven application settings without external dependencies."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AppSettings:
    """Centralized application configuration with basic validation."""

    app_env: str = "development"
    redis_host: str = "redis"
    redis_port: int = 6379
    max_file_size: int = 50 * 1024 * 1024
    rate_limit_requests: int = 10
    rate_limit_window: int = 60
    conversion_timeout: int = 300
    cache_duration: int = 3600
    log_level: str = "INFO"
    log_format: str = "plain"
    log_file: Optional[str] = None

    @staticmethod
    def from_env() -> "AppSettings":
        log_format = os.getenv("LOG_FORMAT", "plain")
        if log_format not in {"plain", "json"}:
            log_format = "plain"

        return AppSettings(
            app_env=os.getenv("APP_ENV", "development"),
            redis_host=os.getenv("REDIS_HOST", "redis"),
            redis_port=_env_int("REDIS_PORT", 6379),
            max_file_size=_env_int("MAX_FILE_SIZE", 50 * 1024 * 1024),
            rate_limit_requests=_env_int("RATE_LIMIT_REQUESTS", 10),
            rate_limit_window=_env_int("RATE_LIMIT_WINDOW", 60),
            conversion_timeout=_env_int("CONVERSION_TIMEOUT", 300),
            cache_duration=_env_int("CACHE_DURATION", 3600),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_format=log_format,
            log_file=os.getenv("LOG_FILE"),
        )

    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache()
def get_settings() -> AppSettings:
    """Load settings from environment once per process."""
    return AppSettings.from_env()
