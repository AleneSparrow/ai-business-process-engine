"""FastAPI application factory and production entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.config import Settings
from src.ai.runtime import build_ai_runtime
from src.engine.customer_response_generator import CustomerResponseGenerator
from src.engine.intent_extractor import IntentExtractor
from src.engine.question_generator import QuestionGenerator
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine

from .dependencies import ApplicationContainer
from .errors import install_error_handlers
from .middleware import RequestContextMiddleware
from .cors import ConfiguredCORSMiddleware
from .rate_limit import InMemorySlidingWindowRateLimiter
from .observability import configure_logging, log_event
from .routes import auth, businesses, health, lead_intake, onboarding, public_conversations


def create_app(
    *,
    settings: Settings | None = None,
    intent_extractor: IntentExtractor | None = None,
    question_generator: QuestionGenerator | None = None,
    customer_response_generator: CustomerResponseGenerator | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_settings = settings or Settings.from_environment()
        configure_logging(runtime_settings.log_level)
        ai_runtime = build_ai_runtime(runtime_settings)
        configured_intent_extractor = intent_extractor or ai_runtime.intent_extractor
        configured_question_generator = question_generator or ai_runtime.question_generator
        configured_response_generator = (
            customer_response_generator or ai_runtime.customer_response_generator
        )
        engine: Engine | None = None
        try:
            engine = create_database_engine(runtime_settings.database_url)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            if engine is not None:
                engine.dispose()
            log_event(
                logging.CRITICAL,
                "application_startup_failed",
                app_env=runtime_settings.app_env,
                error_type=type(exc).__name__,
            )
            raise RuntimeError("API startup failed: database connection is unavailable") from exc

        if engine is None:  # Defensive narrowing; the successful connection path always assigns it.
            raise RuntimeError("API startup failed: database engine was not initialized")
        application.state.container = ApplicationContainer(
            settings=runtime_settings,
            engine=engine,
            unit_of_work_factory=SQLAlchemyUnitOfWork.factory_for_engine(engine),
            intent_extractor=configured_intent_extractor,
            question_generator=configured_question_generator,
            customer_response_generator=configured_response_generator,
            ai_provider_name=ai_runtime.provider_name,
            ai_model_name=ai_runtime.model_name,
            public_chat_rate_limiter=InMemorySlidingWindowRateLimiter(
                runtime_settings.public_chat_rate_limit_requests,
                runtime_settings.public_chat_rate_limit_window_seconds,
            ),
        )
        log_event(
            logging.INFO,
            "application_started",
            app_env=runtime_settings.app_env,
            ai_provider=ai_runtime.provider_name,
            ai_model=ai_runtime.model_name,
        )
        try:
            yield
        finally:
            engine.dispose()
            application.state.container = None
            log_event(logging.INFO, "application_stopped", app_env=runtime_settings.app_env)

    application = FastAPI(
        title="AI Business Process Engine API",
        description=(
            "Tenant-scoped HTTP API for durable lead intake, qualification, website conversations, "
            "and deterministic booking/quoting. "
            "Understanding and response wording use the explicitly configured AI provider; "
            "business decisions remain deterministic and policy-bound."
        ),
        version="0.7.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        RequestContextMiddleware,
        max_request_body_bytes=(settings.max_request_body_bytes if settings else 65_536),
    )
    application.add_middleware(ConfiguredCORSMiddleware)
    install_error_handlers(application)
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(businesses.router)
    application.include_router(onboarding.router)
    application.include_router(lead_intake.router)
    application.include_router(public_conversations.router)
    application.mount(
        "/widget",
        StaticFiles(directory=Path(__file__).parents[2] / "web" / "widget", html=True),
        name="widget",
    )
    return application


app = create_app()
