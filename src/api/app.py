"""FastAPI application factory and production entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.config import Settings
from src.engine.intent_extractor import DeterministicIntentExtractor, IntentExtractor
from src.engine.question_generator import DeterministicQuestionGenerator, QuestionGenerator
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine

from .dependencies import ApplicationContainer
from .errors import install_error_handlers
from .middleware import RequestContextMiddleware
from .observability import configure_logging, log_event
from .routes import businesses, health, lead_intake


def create_app(
    *,
    settings: Settings | None = None,
    intent_extractor: IntentExtractor | None = None,
    question_generator: QuestionGenerator | None = None,
) -> FastAPI:
    configured_intent_extractor = intent_extractor or DeterministicIntentExtractor()
    configured_question_generator = question_generator or DeterministicQuestionGenerator()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_settings = settings or Settings.from_environment()
        configure_logging(runtime_settings.log_level)
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
        )
        log_event(logging.INFO, "application_started", app_env=runtime_settings.app_env)
        try:
            yield
        finally:
            engine.dispose()
            application.state.container = None
            log_event(logging.INFO, "application_stopped", app_env=runtime_settings.app_env)

    application = FastAPI(
        title="AI Business Process Engine API",
        description=(
            "Tenant-scoped HTTP API for durable lead intake and qualification. "
            "The API uses deterministic intent extraction and does not call external AI providers."
        ),
        version="0.4.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        RequestContextMiddleware,
        max_request_body_bytes=(settings.max_request_body_bytes if settings else 65_536),
    )
    install_error_handlers(application)
    application.include_router(health.router)
    application.include_router(businesses.router)
    application.include_router(lead_intake.router)
    return application


app = create_app()
