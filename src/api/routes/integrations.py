"""Optional per-business CRM webhook (e.g. Clio) -- see CrmWebhookService.

Deliberately a dedicated resource, not folded into `/dna`: the webhook URL
is effectively a bearer secret and must never round-trip through the
Business-DNA read/write path (which flows into AI prompt context). The GET
here reports only whether one is configured -- never the URL itself.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.domain.auth import StaffUser
from src.persistence.crm_webhook_service import CrmWebhookService

from ..dependencies import BusinessIdPath, get_crm_webhook_service, require_own_business
from ..errors import RequestDataError
from ..schemas import CrmWebhookConfigureRequest, CrmWebhookStatusResponse

router = APIRouter(prefix="/api/v1/businesses/{business_id}/integrations", tags=["integrations"])


@router.get("/crm-webhook", response_model=CrmWebhookStatusResponse)
def get_crm_webhook_status(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    service: Annotated[CrmWebhookService, Depends(get_crm_webhook_service)],
) -> CrmWebhookStatusResponse:
    return CrmWebhookStatusResponse(configured=service.is_configured(business_id))


@router.put("/crm-webhook", response_model=CrmWebhookStatusResponse)
def configure_crm_webhook(
    business_id: BusinessIdPath,
    body: CrmWebhookConfigureRequest,
    user: Annotated[StaffUser, Depends(require_own_business)],
    service: Annotated[CrmWebhookService, Depends(get_crm_webhook_service)],
) -> CrmWebhookStatusResponse:
    try:
        service.configure(business_id, body.webhook_url)
    except ValueError as exc:
        raise RequestDataError(str(exc)) from exc
    return CrmWebhookStatusResponse(configured=True)


@router.delete("/crm-webhook", response_model=CrmWebhookStatusResponse)
def remove_crm_webhook(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    service: Annotated[CrmWebhookService, Depends(get_crm_webhook_service)],
) -> CrmWebhookStatusResponse:
    service.remove(business_id)
    return CrmWebhookStatusResponse(configured=False)
