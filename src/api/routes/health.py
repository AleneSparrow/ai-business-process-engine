"""Liveness and database-readiness endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..dependencies import ApplicationContainer, get_container
from ..schemas import HealthResponse, ReadinessResponse


router = APIRouter(tags=["service health"])


@router.get("/health", response_model=HealthResponse, summary="Application liveness")
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"description": "PostgreSQL is unavailable"}},
    summary="Application readiness",
)
def ready(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> ReadinessResponse | JSONResponse:
    try:
        with container.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "dependencies": {"database": "unavailable"}},
        )
    return ReadinessResponse(
        status="ready",
        dependencies={"database": "ok", "ai_configuration": "ok"},
    )
