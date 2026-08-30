"""Persisted lead-intake HTTP endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.domain.qualification import IncomingMessage
from src.domain.auth import StaffUser
from src.domain.tenancy import Business
from src.persistence.lead_intake import PersistentLeadIntakeService

from ..dependencies import get_intake_service, require_own_business, resolve_business
from ..errors import RequestDataError, ResourceNotFoundError
from ..schemas import ErrorResponse, IncomingMessageRequest, LeadIntakeResponse


router = APIRouter(prefix="/api/v1/businesses", tags=["lead intake"])


@router.post(
    "/{business_id}/messages",
    response_model=LeadIntakeResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Staff authentication is required"},
        403: {"model": ErrorResponse, "description": "Staff user does not own this business"},
        404: {"model": ErrorResponse, "description": "Business or case not found"},
        409: {"model": ErrorResponse, "description": "Idempotency or concurrency conflict"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
    summary="Receive and qualify a customer message (staff direct intake)",
    description=(
        "Staff-authenticated direct intake for a business owned by the bearer-token caller. "
        "Creates or continues a tenant-scoped lead qualification case. Replaying the same "
        "business, channel, external message ID, and content returns the stored logical result. "
        "Anonymous website chat uses the separate opaque conversation-token routes."
    ),
)
def receive_message(
    request: Request,
    payload: IncomingMessageRequest,
    user: Annotated[StaffUser, Depends(require_own_business)],
    business: Annotated[Business, Depends(resolve_business)],
    intake_service: Annotated[PersistentLeadIntakeService, Depends(get_intake_service)],
) -> LeadIntakeResponse:
    try:
        message = IncomingMessage(
            business_id=business.business_id,
            channel=payload.channel,
            external_message_id=payload.external_message_id,
            raw_text=payload.message,
            timestamp=payload.timestamp,
            customer_name=payload.customer_name,
            phone=payload.phone,
            email=payload.email,
            case_id=payload.case_id,
        )
    except (TypeError, ValueError) as exc:
        raise RequestDataError() from exc

    try:
        result = intake_service.receive(message)
    except KeyError as exc:
        raise ResourceNotFoundError("case_not_found", "Case was not found for this business") from exc

    request.state.resulting_state = result.current_state.value
    return LeadIntakeResponse.from_result(business.business_id, result)
