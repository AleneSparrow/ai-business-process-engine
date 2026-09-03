"""Inbound inquiries from the Flywheel Demand product.

Demand is a separate engine. It posts ordinary intake JSON here after a
person inquires. Flywheel opens a case at NEW_LEAD. This route is not
staff-authenticated: Demand calls it with the same internal task secret
as the sweep endpoints. Entitlement is `Business.has_demand_access`.
"""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from src.domain.qualification import IncomingMessage
from src.domain.tenancy import Business
from src.persistence.errors import DemandSubscriptionRequiredError
from src.persistence.lead_intake import PersistentLeadIntakeService

from ..dependencies import (
    ApplicationContainer,
    get_container,
    get_intake_service,
    resolve_business,
)
from ..errors import RequestDataError, ResourceNotFoundError, UnauthorizedError
from ..schemas import DemandInquiryRequest, ErrorResponse, LeadIntakeResponse


router = APIRouter(prefix="/api/v1/businesses", tags=["demand"])


def _require_task_secret(container: ApplicationContainer, provided: str | None) -> None:
    configured = container.settings.internal_task_secret
    if not configured:
        raise UnauthorizedError("Demand intake is not enabled on this deployment")
    if not provided or not hmac.compare_digest(provided, configured):
        raise UnauthorizedError("Invalid or missing internal task secret")


@router.post(
    "/{business_id}/demand/inquiries",
    response_model=LeadIntakeResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Internal task secret is required"},
        402: {"model": ErrorResponse, "description": "Demand add-on is not active"},
        404: {"model": ErrorResponse, "description": "Business or case not found"},
        409: {"model": ErrorResponse, "description": "Idempotency or concurrency conflict"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
    summary="Accept a Flywheel Demand inquiry into NEW_LEAD",
)
def receive_demand_inquiry(
    request: Request,
    payload: DemandInquiryRequest,
    business: Annotated[Business, Depends(resolve_business)],
    intake_service: Annotated[PersistentLeadIntakeService, Depends(get_intake_service)],
    container: Annotated[ApplicationContainer, Depends(get_container)],
    x_internal_task_secret: Annotated[str | None, Header()] = None,
) -> LeadIntakeResponse:
    _require_task_secret(container, x_internal_task_secret)
    if payload.business_id != business.business_id:
        raise RequestDataError("business_id in the payload must match the path")
    if not business.has_demand_access:
        raise DemandSubscriptionRequiredError(
            "Demand inquiries are rejected until the Demand add-on is active"
        )
    try:
        message = IncomingMessage(
            business_id=business.business_id,
            channel=payload.channel,
            external_message_id=payload.external_message_id,
            raw_text=payload.raw_text,
            timestamp=payload.timestamp,
            customer_name=payload.customer_name,
            phone=payload.phone,
            email=payload.email,
            sms_consent=payload.sms_consent,
        )
    except (TypeError, ValueError) as exc:
        raise RequestDataError() from exc

    try:
        result = intake_service.receive(message)
    except KeyError as exc:
        raise ResourceNotFoundError("case_not_found", "Case was not found for this business") from exc

    request.state.resulting_state = result.current_state.value
    return LeadIntakeResponse.from_result(business.business_id, result)
