"""Safe translation from application failures to public HTTP errors."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.persistence.errors import (
    IdempotencyCollisionError,
    IdempotencyInProgressError,
    MessageScopeError,
    StaleCaseError,
)

from .observability import log_event
from .schemas import validation_issues


class PublicApiError(Exception):
    def __init__(self, status_code: int, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.status_code = status_code
        self.code = code
        self.public_message = public_message


class ResourceNotFoundError(PublicApiError):
    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(404, code, public_message)


class RequestDataError(PublicApiError):
    def __init__(self, public_message: str = "Request data is invalid") -> None:
        super().__init__(422, "invalid_request", public_message)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unavailable"))


def _response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    content: dict[str, Any] = {
        "error": {"code": code, "message": message, "request_id": request_id}
    }
    if details is not None:
        content["error"]["details"] = details
    response_headers = {"X-Request-ID": request_id, **(headers or {})}
    return JSONResponse(status_code=status_code, content=content, headers=response_headers)


def _log_error(request: Request, code: str, status_code: int, error_type: str) -> None:
    log_event(
        logging.ERROR if status_code >= 500 else logging.WARNING,
        "http_request_error",
        request_id=_request_id(request),
        business_id=getattr(request.state, "business_id", None),
        endpoint=request.url.path,
        status_code=status_code,
        error_code=code,
        error_type=error_type,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PublicApiError)
    async def public_api_error_handler(request: Request, exc: PublicApiError) -> JSONResponse:
        _log_error(request, exc.code, exc.status_code, type(exc).__name__)
        return _response(request, exc.status_code, exc.code, exc.public_message)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        code = "validation_error"
        _log_error(request, code, 422, type(exc).__name__)
        return _response(
            request,
            422,
            code,
            "Request validation failed",
            details=validation_issues(exc.errors()),
        )

    @app.exception_handler(IdempotencyCollisionError)
    async def idempotency_collision_handler(
        request: Request, exc: IdempotencyCollisionError
    ) -> JSONResponse:
        code = "idempotency_collision"
        _log_error(request, code, 409, type(exc).__name__)
        return _response(
            request,
            409,
            code,
            "The message identity was already used for different content",
        )

    @app.exception_handler(StaleCaseError)
    async def stale_case_handler(request: Request, exc: StaleCaseError) -> JSONResponse:
        code = "concurrency_conflict"
        _log_error(request, code, 409, type(exc).__name__)
        return _response(request, 409, code, "The case changed concurrently; retry the request")

    @app.exception_handler(MessageScopeError)
    async def message_scope_handler(request: Request, exc: MessageScopeError) -> JSONResponse:
        code = "message_not_accepted"
        _log_error(request, code, 422, type(exc).__name__)
        return _response(
            request,
            422,
            code,
            "The message channel is not enabled for this business",
        )

    @app.exception_handler(IdempotencyInProgressError)
    async def idempotency_invariant_handler(
        request: Request, exc: IdempotencyInProgressError
    ) -> JSONResponse:
        code = "idempotency_temporarily_unavailable"
        _log_error(request, code, 503, type(exc).__name__)
        return _response(
            request,
            503,
            code,
            "The message result is temporarily unavailable; retry later",
            headers={"Retry-After": "1"},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        code = "internal_error"
        _log_error(request, code, 500, type(exc).__name__)
        return _response(request, 500, code, "An unexpected internal error occurred")
