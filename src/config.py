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
    cors_allowed_origins: tuple[str, ...] = ()
    public_chat_rate_limit_requests: int = 20
    public_chat_rate_limit_window_seconds: int = 60
    public_conversation_token_ttl_hours: int = 720
    public_chat_message_max_chars: int = 2_000

    def __post_init__(self) -> None:
        if not self.database_url.strip():
            raise ValueError("database_url must not be empty")
        if not 1_024 <= self.max_request_body_bytes <= 10_485_760:
            raise ValueError("max_request_body_bytes must be between 1024 and 10485760")
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
        if self.app_env.casefold() in {"production", "prod"} and "*" in self.cors_allowed_origins:
            raise ValueError("wildcard CORS origins are not allowed in production")
        if not 1 <= self.public_chat_rate_limit_requests <= 10_000:
            raise ValueError("public chat rate limit must be between 1 and 10000")
        if not 1 <= self.public_chat_rate_limit_window_seconds <= 3_600:
            raise ValueError("public chat rate limit window must be between 1 and 3600 seconds")
        if not 1 <= self.public_conversation_token_ttl_hours <= 8_760:
            raise ValueError("public conversation token TTL must be between 1 and 8760 hours")
        if not 100 <= self.public_chat_message_max_chars <= 10_000:
            raise ValueError("public chat message maximum must be between 100 and 10000")

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
            max_request_body_bytes = int(os.getenv("MAX_REQUEST_BODY_BYTES", "65536"))
            rate_limit_requests = int(os.getenv("PUBLIC_CHAT_RATE_LIMIT_REQUESTS", "20"))
            rate_limit_window = int(os.getenv("PUBLIC_CHAT_RATE_LIMIT_WINDOW_SECONDS", "60"))
            token_ttl = int(os.getenv("PUBLIC_CONVERSATION_TOKEN_TTL_HOURS", "720"))
            message_max = int(os.getenv("PUBLIC_CHAT_MESSAGE_MAX_CHARS", "2000"))
        except ValueError as exc:
            raise RuntimeError("numeric application settings contain an invalid value") from exc
        origins = tuple(
            value.strip()
            for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
            if value.strip()
        )
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
                max_request_body_bytes=max_request_body_bytes,
                cors_allowed_origins=origins,
                public_chat_rate_limit_requests=rate_limit_requests,
                public_chat_rate_limit_window_seconds=rate_limit_window,
                public_conversation_token_ttl_hours=token_ttl,
                public_chat_message_max_chars=message_max,
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

    @staticmethod
    def database_url_from_environment() -> str:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        return database_url
