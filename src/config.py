"""Application configuration loaded exclusively from environment variables."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_env: str = "development"
    log_level: str = "INFO"
    max_request_body_bytes: int = 65_536
    ai_provider: str = "deterministic"
    openai_api_key: str | None = field(default=None, repr=False)
    openai_model: str | None = None
    ai_timeout_seconds: float = 20.0
    ai_max_retries: int = 2

    def __post_init__(self) -> None:
        if not self.database_url.strip():
            raise ValueError("database_url must not be empty")
        if self.ai_provider not in {"deterministic", "openai"}:
            raise ValueError("ai_provider must be 'deterministic' or 'openai'")
        if not 0 < self.ai_timeout_seconds <= 120:
            raise ValueError("ai_timeout_seconds must be greater than 0 and at most 120")
        if not 0 <= self.ai_max_retries <= 3:
            raise ValueError("ai_max_retries must be between 0 and 3")
        if self.ai_provider == "openai":
            if self.openai_api_key is None or not self.openai_api_key.strip():
                raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
            if self.openai_model is None or not self.openai_model.strip():
                raise ValueError("OPENAI_MODEL is required when AI_PROVIDER=openai")

    @classmethod
    def from_environment(cls) -> "Settings":
        database_url = cls.database_url_from_environment()
        app_env = os.getenv("APP_ENV", "development").strip()
        if not app_env:
            raise RuntimeError("APP_ENV must not be empty")
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise RuntimeError("LOG_LEVEL must be a standard Python logging level")
        ai_provider_value = os.getenv("AI_PROVIDER")
        if ai_provider_value is None or not ai_provider_value.strip():
            raise RuntimeError("AI_PROVIDER is required and must be explicitly configured")
        ai_provider = ai_provider_value.strip().casefold()
        try:
            ai_timeout_seconds = float(os.getenv("AI_TIMEOUT_SECONDS", "20"))
            ai_max_retries = int(os.getenv("AI_MAX_RETRIES", "2"))
        except ValueError as exc:
            raise RuntimeError("AI timeout and retry settings must be numeric") from exc
        try:
            return cls(
                database_url=database_url,
                app_env=app_env,
                log_level=log_level,
                ai_provider=ai_provider,
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                openai_model=os.getenv("OPENAI_MODEL"),
                ai_timeout_seconds=ai_timeout_seconds,
                ai_max_retries=ai_max_retries,
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

    @staticmethod
    def database_url_from_environment() -> str:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        return database_url
