"""外部依存なく環境変数から設定を読み込む。"""
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
    """アプリ設定を一元管理し、簡易バリデーションを行う。"""

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
    enable_memory_profiling: bool = False
    memory_profiling_interval: int = 60

    @staticmethod
    def from_env() -> "AppSettings":
        log_format = os.getenv("LOG_FORMAT", "plain")
        if log_format not in {"plain", "json"}:
            log_format = "plain"

        enable_memory_profiling = os.getenv("ENABLE_MEMORY_PROFILING", "false").lower() == "true"

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
            enable_memory_profiling=enable_memory_profiling,
            memory_profiling_interval=_env_int("MEMORY_PROFILING_INTERVAL", 60),
        )

    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache()
def get_settings() -> AppSettings:
    """環境変数から設定を読み込み、プロセス内で1回だけ評価する。"""
    return AppSettings.from_env()
