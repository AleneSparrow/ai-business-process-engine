"""Application configuration loaded exclusively from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_env: str = "development"
    log_level: str = "INFO"
    max_request_body_bytes: int = 65_536

    @classmethod
    def from_environment(cls) -> "Settings":
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        app_env = os.getenv("APP_ENV", "development").strip()
        if not app_env:
            raise RuntimeError("APP_ENV must not be empty")
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise RuntimeError("LOG_LEVEL must be a standard Python logging level")
        return cls(database_url=database_url, app_env=app_env, log_level=log_level)
