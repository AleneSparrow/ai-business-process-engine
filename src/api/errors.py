"""Safe translation from application failures to public HTTP errors."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.ai.errors import AIInvalidOutputError, AIProviderError
from src.persistence.auth_service import EmailAlreadyRegisteredError, InvalidCredentialsError
from src.persistence.business_provisioning_service import (
    AccountAlreadyHasBusinessError,
    BusinessIdTakenError,
    InvalidBusinessDNAError,
)
from src.persistence.errors import (
    BillingAccountNotFoundError,
    BillingNotConfiguredError,
    CaseNotAwaitingApprovalError,
    ConversationClosedError,
    ConversationNotLinkedError,
    ConversationTokenError,
    ConversationTokenExpiredError,
    IdempotencyCollisionError,
    IdempotencyInProgressError,
    InvalidPlanError,
    MessageScopeError,
    StaffConversationNotFoundError,
    StaleCaseError,
    WebhookSignatureError,
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


class UnauthorizedError(PublicApiError):
    def __init__(self, public_message: str = "Authentication is required") -> None:
        super().__init__(401, "unauthorized", public_message)


class ForbiddenError(PublicApiError):
    def __init__(self, public_message: str = "Not permitted for this account") -> None:
        super().__init__(403, "forbidden", public_message)


class ConflictError(PublicApiError):
    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(409, code, public_message)


class PaymentRequiredError(PublicApiError):
    def __init__(
        self,
        public_message: str = "This business's Atelier subscription needs attention before the dashboard is available",
    ) -> None:
        super().__init__(402, "subscription_inactive", public_message)


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


def _log_error(
    request: Request,
    code: str,
    status_code: int,
    error_type: str,
    **safe_fields: object,
) -> None:
    log_event(
        logging.ERROR if status_code >= 500 else logging.WARNING,
        "http_request_error",
        request_id=_request_id(request),
        business_id=getattr(request.state, "business_id", None),
        endpoint=getattr(request.scope.get("route"), "path", "unmatched"),
        status_code=status_code,
        error_code=code,
        error_type=error_type,
        **safe_fields,
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

    @app.exception_handler(ConversationTokenExpiredError)
    async def conversation_expired_handler(
        request: Request, exc: ConversationTokenExpiredError
    ) -> JSONResponse:
        code = "conversation_expired"
        _log_error(request, code, 410, type(exc).__name__)
        return _response(request, 410, code, "The conversation session has expired")

    @app.exception_handler(ConversationTokenError)
    async def conversation_token_handler(
        request: Request, exc: ConversationTokenError
    ) -> JSONResponse:
        code = "conversation_not_found"
        _log_error(request, code, 404, type(exc).__name__)
        return _response(request, 404, code, "Conversation was not found")

    @app.exception_handler(StaleCaseError)
    async def stale_case_handler(request: Request, exc: StaleCaseError) -> JSONResponse:
        code = "concurrency_conflict"
        _log_error(request, code, 409, type(exc).__name__)
        return _response(request, 409, code, "The case changed concurrently; retry the request")

    @app.exception_handler(StaffConversationNotFoundError)
    async def staff_conversation_not_found_handler(
        request: Request, exc: StaffConversationNotFoundError
    ) -> JSONResponse:
        code = "conversation_not_found"
        _log_error(request, code, 404, type(exc).__name__)
        return _response(request, 404, code, "Conversation was not found")

    @app.exception_handler(ConversationNotLinkedError)
    async def conversation_not_linked_handler(
        request: Request, exc: ConversationNotLinkedError
    ) -> JSONResponse:
        code = "conversation_not_linked"
        _log_error(request, code, 422, type(exc).__name__)
        return _response(request, 422, code, str(exc))

    @app.exception_handler(ConversationClosedError)
    async def conversation_closed_handler(request: Request, exc: ConversationClosedError) -> JSONResponse:
        code = "conversation_closed"
        _log_error(request, code, 409, type(exc).__name__)
        return _response(request, 409, code, "This conversation is already closed")

    @app.exception_handler(CaseNotAwaitingApprovalError)
    async def case_not_awaiting_approval_handler(
        request: Request, exc: CaseNotAwaitingApprovalError
    ) -> JSONResponse:
        code = "case_not_awaiting_approval"
        _log_error(request, code, 409, type(exc).__name__)
        return _response(request, 409, code, "This case isn't waiting on human approval right now")

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

    @app.exception_handler(AIProviderError)
    async def ai_provider_error_handler(request: Request, exc: AIProviderError) -> JSONResponse:
        if isinstance(exc, AIInvalidOutputError):
            code = "ai_output_invalid"
            message = "The AI response could not be safely validated; retry later"
        elif exc.transient:
            code = "ai_temporarily_unavailable"
            message = "The AI provider is temporarily unavailable; retry later"
        else:
            code = "ai_provider_unavailable"
            message = "The configured AI provider is unavailable"
        metadata = exc.metadata
        _log_error(
            request,
            code,
            503,
            type(exc).__name__,
            ai_provider=metadata.provider if metadata else None,
            ai_model=metadata.model if metadata else None,
            ai_prompt_id=metadata.prompt_id if metadata else None,
            ai_prompt_version=metadata.prompt_version if metadata else None,
            ai_category=metadata.category if metadata else exc.category,
            ai_attempts=metadata.attempts if metadata else None,
        )
        return _response(
            request,
            503,
            code,
            message,
            headers={"Retry-After": "1"} if exc.transient else None,
        )

    @app.exception_handler(EmailAlreadyRegisteredError)
    async def email_already_registered_handler(
        request: Request, exc: EmailAlreadyRegisteredError
    ) -> JSONResponse:
        code = "email_already_registered"
        _log_error(request, code, 409, type(exc).__name__)
        return _response(request, 409, code, "An account with this email already exists")

    @app.exception_handler(InvalidCredentialsError)
    async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
        code = "invalid_credentials"
        _log_error(request, code, 401, type(exc).__name__)
        return _response(request, 401, code, "Email or password is incorrect")

    @app.exception_handler(AccountAlreadyHasBusinessError)
    async def account_already_has_business_handler(
        request: Request, exc: AccountAlreadyHasBusinessError
    ) -> JSONResponse:
        code = "account_already_has_business"
        _log_error(request, code, 409, type(exc).__name__)
        return _response(request, 409, code, "This account is already linked to a business")

    @app.exception_handler(BusinessIdTakenError)
    async def business_id_taken_handler(request: Request, exc: BusinessIdTakenError) -> JSONResponse:
        code = "business_id_taken"
        _log_error(request, code, 409, type(exc).__name__)
        return _response(request, 409, code, "A business with this name is already registered")

    @app.exception_handler(InvalidBusinessDNAError)
    async def invalid_business_dna_handler(request: Request, exc: InvalidBusinessDNAError) -> JSONResponse:
        code = "invalid_business_dna"
        _log_error(request, code, 422, type(exc).__name__)
        return _response(
            request,
            422,
            code,
            "That change would produce an invalid business configuration",
            details=[{"message": str(exc)}],
        )

    @app.exception_handler(BillingNotConfiguredError)
    async def billing_not_configured_handler(
        request: Request, exc: BillingNotConfiguredError
    ) -> JSONResponse:
        code = "billing_not_configured"
        _log_error(request, code, 503, type(exc).__name__)
        return _response(request, 503, code, "Billing is not available on this deployment yet")

    @app.exception_handler(InvalidPlanError)
    async def invalid_plan_handler(request: Request, exc: InvalidPlanError) -> JSONResponse:
        code = "invalid_plan"
        _log_error(request, code, 422, type(exc).__name__)
        return _response(request, 422, code, "That plan isn't available")

    @app.exception_handler(BillingAccountNotFoundError)
    async def billing_account_not_found_handler(
        request: Request, exc: BillingAccountNotFoundError
    ) -> JSONResponse:
        code = "billing_account_not_found"
        _log_error(request, code, 409, type(exc).__name__)
        return _response(request, 409, code, "This business hasn't started a subscription yet")

    @app.exception_handler(WebhookSignatureError)
    async def webhook_signature_handler(request: Request, exc: WebhookSignatureError) -> JSONResponse:
        code = "webhook_signature_invalid"
        _log_error(request, code, 400, type(exc).__name__)
        return _response(request, 400, code, "Webhook signature verification failed")

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        code = "internal_error"
        _log_error(request, code, 500, type(exc).__name__)
        return _response(request, 500, code, "An unexpected internal error occurred")
