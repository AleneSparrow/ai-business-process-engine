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
    stripe_secret_key: str | None = field(default=None, repr=False)
    stripe_webhook_secret: str | None = field(default=None, repr=False)
    stripe_price_starter: str | None = None
    stripe_price_pro: str | None = None
    billing_trial_days: int = 7
    frontend_base_url: str | None = None

    @property
    def billing_configured(self) -> bool:
        """Whether Stripe billing is wired up. Deliberately optional at the Settings
        level (unlike ai_provider) so local dev and early deploys can boot without a
        Stripe account -- BillingService raises a clear, specific error per-request
        instead of failing the whole app at startup."""
        return self.stripe_secret_key is not None

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
        if not 0 <= self.billing_trial_days <= 90:
            raise ValueError("billing_trial_days must be between 0 and 90")
        if self.billing_configured:
            missing = [
                name
                for name, value in (
                    ("STRIPE_WEBHOOK_SECRET", self.stripe_webhook_secret),
                    ("STRIPE_PRICE_STARTER", self.stripe_price_starter),
                    ("STRIPE_PRICE_PRO", self.stripe_price_pro),
                    ("FRONTEND_BASE_URL", self.frontend_base_url),
                )
                if not value or not value.strip()
            ]
            if missing:
                raise ValueError(
                    "STRIPE_SECRET_KEY is set, so billing is enabled -- also required: "
                    + ", ".join(missing)
                )

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
            billing_trial_days = int(os.getenv("BILLING_TRIAL_DAYS", "7"))
        except ValueError as exc:
            raise RuntimeError("numeric application settings contain an invalid value") from exc
        origins = tuple(
            value.strip()
            for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
            if value.strip()
        )
        frontend_base_url = os.getenv("FRONTEND_BASE_URL")
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
                stripe_secret_key=os.getenv("STRIPE_SECRET_KEY"),
                stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET"),
                stripe_price_starter=os.getenv("STRIPE_PRICE_STARTER"),
                stripe_price_pro=os.getenv("STRIPE_PRICE_PRO"),
                billing_trial_days=billing_trial_days,
                frontend_base_url=frontend_base_url.rstrip("/") if frontend_base_url else None,
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

    @staticmethod
    def database_url_from_environment() -> str:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        return database_url
