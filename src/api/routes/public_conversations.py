"""Anonymous, token-scoped website conversation API."""

import hashlib
from typing import Annotated, Any, Mapping

from fastapi import APIRouter, Depends, Path, Request

from src.domain.tenancy import Business
from src.persistence.conversation_service import ConversationService
from src.persistence.crm_webhook_service import CrmWebhookService

from ..dependencies import (
    ApplicationContainer,
    get_container,
    get_conversation_service,
    get_crm_webhook_service,
    get_public_chat_rate_limiter,
    resolve_business,
)
from ..errors import PublicApiError, RequestDataError
from ..rate_limit import RateLimiter
from ..schemas import (
    ErrorResponse,
    PublicChatConfigResponse,
    PublicCommercialResponse,
    PublicConversationCreateRequest,
    PublicConversationMessageRequest,
    PublicConversationResponse,
)


router = APIRouter(prefix="/api/v1/public/businesses", tags=["public conversations"])
ConversationTokenPath = Annotated[
    str,
    Path(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _enforce_rate_limit(limiter: RateLimiter, key: str) -> None:
    if not limiter.allow(key):
        raise PublicApiError(429, "rate_limit_exceeded", "Too many chat requests; try again later")


def _notify_crm_if_relevant(
    crm_webhook_service: CrmWebhookService,
    business_id: str,
    result: object,
) -> None:
    """Fire the optional CRM webhook (see CrmWebhookService) *after* the state
    transition below has already committed -- `result` here is always the
    return value of a completed, committed service call, never state read
    mid-transaction. Best-effort: `notify_if_configured` never raises."""
    current_state = getattr(result, "current_state", None)
    conversation_id = getattr(result, "internal_conversation_id", None)
    if current_state is None or conversation_id is None:
        return
    crm_webhook_service.notify_if_configured(
        business_id,
        conversation_id=conversation_id,
        state=current_state.value,
    )


def _validate_message_length(message: str, container: ApplicationContainer) -> None:
    if len(message) > container.settings.public_chat_message_max_chars:
        raise RequestDataError("Chat message exceeds the configured size limit")


@router.get(
    "/{business_id}/chat-config",
    response_model=PublicChatConfigResponse,
    responses={404: {"model": ErrorResponse, "description": "Business not found"}},
    summary="Get safe website chat configuration",
)
def get_chat_config(
    business: Annotated[Business, Depends(resolve_business)],
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> PublicChatConfigResponse:
    with container.unit_of_work_factory() as uow:
        version = uow.business_dna.get_active(business.business_id)
    if version is None:
        raise RuntimeError("business has no active Business DNA")
    dna: Mapping[str, Any] = version.configuration
    widget = dna.get("chat_widget", {})
    communication = dna.get("communication", {})
    channels = communication.get("channels", []) if isinstance(communication, Mapping) else []
    return PublicChatConfigResponse(
        enabled=(
            bool(widget.get("enabled", False)) and "webchat" in channels
            if isinstance(widget, Mapping)
            else False
        ),
        business_name=business.name,
        chat_title=(
            str(widget.get("title", business.name))
            if isinstance(widget, Mapping)
            else business.name
        ),
        welcome_message=(
            str(widget.get("welcome_message", "How can we help?"))
            if isinstance(widget, Mapping)
            else "How can we help?"
        ),
        language=(
            str(communication.get("language", "English"))
            if isinstance(communication, Mapping)
            else "English"
        ),
        ai_disclosure_text=(
            str(widget.get("ai_disclosure_text", ""))
            if isinstance(widget, Mapping)
            else ""
        ),
    )


@router.post(
    "/{business_id}/conversations",
    response_model=PublicConversationResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Business not found"},
        422: {"model": ErrorResponse, "description": "Public chat is disabled or data is invalid"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Create an anonymous website conversation",
)
def create_conversation(
    request: Request,
    payload: PublicConversationCreateRequest,
    business: Annotated[Business, Depends(resolve_business)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    limiter: Annotated[RateLimiter, Depends(get_public_chat_rate_limiter)],
    container: Annotated[ApplicationContainer, Depends(get_container)],
    crm_webhook_service: Annotated[CrmWebhookService, Depends(get_crm_webhook_service)],
) -> PublicConversationResponse:
    _enforce_rate_limit(limiter, f"create:{business.business_id}:{_client_ip(request)}")
    if payload.message is not None:
        _validate_message_length(payload.message, container)
        request.state.message_direction = "inbound"
    result = service.create(
        business.business_id,
        message_text=payload.message,
        external_message_id=payload.external_message_id,
        correlation_id=getattr(request.state, "request_id", None),
        conversation_token=payload.conversation_token,
    )
    request.state.conversation_id = result.internal_conversation_id
    request.state.resulting_state = result.current_state.value if result.current_state else None
    _notify_crm_if_relevant(crm_webhook_service, business.business_id, result)
    return PublicConversationResponse.from_domain(result)


@router.post(
    "/{business_id}/conversations/{conversation_token}/messages",
    response_model=PublicConversationResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Conversation not found"},
        409: {"model": ErrorResponse, "description": "Message identity collision"},
        410: {"model": ErrorResponse, "description": "Conversation expired"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Send a follow-up website chat message",
)
def send_conversation_message(
    request: Request,
    payload: PublicConversationMessageRequest,
    business: Annotated[Business, Depends(resolve_business)],
    conversation_token: ConversationTokenPath,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    limiter: Annotated[RateLimiter, Depends(get_public_chat_rate_limiter)],
    container: Annotated[ApplicationContainer, Depends(get_container)],
    crm_webhook_service: Annotated[CrmWebhookService, Depends(get_crm_webhook_service)],
) -> PublicConversationResponse:
    token_key = hashlib.sha256(conversation_token.encode("utf-8")).hexdigest()
    _enforce_rate_limit(
        limiter,
        f"message:{business.business_id}:{_client_ip(request)}:{token_key}",
    )
    _validate_message_length(payload.message, container)
    request.state.message_direction = "inbound"
    result = service.send_message(
        business.business_id,
        conversation_token,
        message_text=payload.message,
        external_message_id=payload.external_message_id,
        correlation_id=getattr(request.state, "request_id", None),
    )
    request.state.conversation_id = result.internal_conversation_id
    request.state.resulting_state = result.current_state.value if result.current_state else None
    _notify_crm_if_relevant(crm_webhook_service, business.business_id, result)
    return PublicConversationResponse.from_domain(result)


@router.get(
    "/{business_id}/conversations/{conversation_token}",
    response_model=PublicConversationResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Conversation not found"},
        410: {"model": ErrorResponse, "description": "Conversation expired"},
    },
    summary="Restore safe website conversation history",
)
def get_conversation(
    request: Request,
    business: Annotated[Business, Depends(resolve_business)],
    conversation_token: ConversationTokenPath,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> PublicConversationResponse:
    result = service.get(business.business_id, conversation_token)
    request.state.conversation_id = result.internal_conversation_id
    request.state.resulting_state = result.current_state.value if result.current_state else None
    return PublicConversationResponse.from_domain(result)


@router.get(
    "/{business_id}/conversations/{conversation_token}/commercial",
    response_model=PublicCommercialResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Conversation not found"},
        410: {"model": ErrorResponse, "description": "Conversation expired"},
    },
    summary="Get token-owned booking, quote, and payment-request status",
)
def get_conversation_commercial(
    request: Request,
    business: Annotated[Business, Depends(resolve_business)],
    conversation_token: ConversationTokenPath,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> PublicCommercialResponse:
    result = service.get_commercial(business.business_id, conversation_token)
    request.state.resulting_state = (
        result.current_state.value if result.current_state else None
    )
    return PublicCommercialResponse.from_domain(result)
