"""Self-serve Lemon Squeezy subscription billing.

Two route groups on purpose:

- `/api/v1/businesses/{business_id}/billing*` -- staff-authenticated, scoped
  to the caller's own business via `require_own_business` (same pattern as
  dashboard.py / business_dna.py). Deliberately NOT gated by
  `require_active_subscription` -- this is where an owner goes precisely
  *because* their subscription needs attention.
- `/api/v1/billing/webhook` -- called directly by Lemon Squeezy, not a
  browser. No staff auth (Lemon Squeezy doesn't have a session token);
  authenticity comes from the X-Signature header instead, verified inside
  `BillingService.handle_webhook`. Raw body bytes are required for that
  verification, so this route reads the body directly rather than
  declaring a Pydantic model.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from src.domain.auth import StaffUser
from src.persistence.billing_service import BillingService

from ..dependencies import BusinessIdPath, get_billing_service, require_own_business
from ..errors import RequestDataError
from ..schemas import (
    BillingStatusResponse,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PortalSessionResponse,
)

router = APIRouter(prefix="/api/v1/businesses/{business_id}/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("", response_model=BillingStatusResponse)
def get_billing_status(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
) -> BillingStatusResponse:
    return BillingStatusResponse.from_domain(billing_service.get_status(business_id))


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
def create_checkout_session(
    business_id: BusinessIdPath,
    body: CheckoutSessionRequest,
    user: Annotated[StaffUser, Depends(require_own_business)],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
) -> CheckoutSessionResponse:
    url = billing_service.create_checkout_session(business_id, body.plan, user.email)
    return CheckoutSessionResponse(checkout_url=url)


@router.post("/portal-session", response_model=PortalSessionResponse)
def create_portal_session(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
) -> PortalSessionResponse:
    url = billing_service.create_portal_session(business_id)
    return PortalSessionResponse(portal_url=url)


@webhook_router.post("/webhook", status_code=status.HTTP_200_OK)
async def lemonsqueezy_webhook(
    request: Request,
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
) -> dict:
    if not x_signature:
        raise RequestDataError("Missing X-Signature header")
    payload = await request.body()
    billing_service.handle_webhook(payload, x_signature)
    return {"received": True}
