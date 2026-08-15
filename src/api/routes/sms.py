"""SMS delivery: inbound Twilio webhook (public, signature-verified) and the
authenticated per-business status/retry endpoints.

The inbound webhook is deliberately NOT under `/api/v1/public/businesses/
{business_id}/...` like the web-chat conversation API -- Twilio doesn't know
a business_id, only the phone number a text arrived on, so the business is
resolved from that number via `SmsService.resolve_business_id_by_phone`.
Authenticity here rests entirely on the Twilio request signature (see
`twilio_client.validate_inbound_signature`), not on a hard-to-guess URL.

Reuses `PersistentLeadIntakeService` -- the same channel-agnostic engine
entry point `/api/v1/businesses/{business_id}/messages` uses -- rather than
the anonymous web-chat conversation flow, since a text message already
carries a stable identity (the sender's phone number) and has no browser
token to manage.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response

from src.domain.auth import StaffUser
from src.domain.models import utc_now
from src.domain.qualification import IncomingMessage
from src.persistence.errors import WebhookSignatureError
from src.persistence.lead_intake import PersistentLeadIntakeService
from src.persistence.sms_service import INBOUND_SMS_WEBHOOK_PATH, SmsService
from src.persistence.twilio_client import validate_inbound_signature

from ..dependencies import (
    ApplicationContainer,
    BusinessIdPath,
    get_container,
    get_intake_service,
    get_sms_service,
    require_own_business,
)
from ..errors import RequestDataError, ResourceNotFoundError
from ..schemas import SmsStatusResponse

public_router = APIRouter(prefix="/api/v1/public/sms", tags=["sms"])
router = APIRouter(prefix="/api/v1/businesses/{business_id}/integrations", tags=["integrations"])

_EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@public_router.post("/inbound", status_code=200)
async def receive_inbound_sms(
    request: Request,
    container: Annotated[ApplicationContainer, Depends(get_container)],
    sms_service: Annotated[SmsService, Depends(get_sms_service)],
    intake_service: Annotated[PersistentLeadIntakeService, Depends(get_intake_service)],
    x_twilio_signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> Response:
    if not x_twilio_signature or not container.settings.twilio_auth_token:
        raise WebhookSignatureError("Missing X-Twilio-Signature header, or SMS is not configured")

    form = await request.form()
    form_params = {key: str(value) for key, value in form.items()}
    validation_url = f"{container.settings.public_api_base_url}{INBOUND_SMS_WEBHOOK_PATH}"
    if not validate_inbound_signature(
        container.settings.twilio_auth_token,
        url=validation_url,
        form_params=form_params,
        signature=x_twilio_signature,
    ):
        raise WebhookSignatureError("Twilio request signature did not match")

    from_number = form_params.get("From")
    to_number = form_params.get("To")
    body = form_params.get("Body", "")
    message_sid = form_params.get("MessageSid")
    if not from_number or not to_number or not message_sid:
        raise RequestDataError("Missing From/To/MessageSid in Twilio webhook payload")

    business_id = sms_service.resolve_business_id_by_phone(to_number)
    if business_id is None:
        # A number Twilio still has registered but we no longer recognize --
        # nothing to route to. Acknowledge with empty TwiML so Twilio doesn't
        # retry; there's no business-scoped error channel to report this to.
        return Response(content=_EMPTY_TWIML, media_type="application/xml")

    message = IncomingMessage(
        business_id=business_id,
        channel="sms",
        external_message_id=message_sid,
        raw_text=body,
        timestamp=utc_now(),
        phone=from_number,
    )
    result = intake_service.receive(message)
    if result.response is not None:
        sms_service.send_outbound(
            business_id, to_number=from_number, body=result.response.message_text
        )
    return Response(content=_EMPTY_TWIML, media_type="application/xml")


@router.get("/sms", response_model=SmsStatusResponse)
def get_sms_status(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    service: Annotated[SmsService, Depends(get_sms_service)],
) -> SmsStatusResponse:
    return SmsStatusResponse(configured=service.configured, phone_number=service.get_number(business_id))


@router.post("/sms/provision", response_model=SmsStatusResponse)
def provision_sms_number(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    service: Annotated[SmsService, Depends(get_sms_service)],
) -> SmsStatusResponse:
    """Provisioning is manual, not automatic on signup (each number is a real
    recurring Twilio charge). This is the only place a number gets bought --
    called by the Settings 'Set up SMS' button, and idempotently retried by
    the same button (relabelled 'Retry') if an earlier attempt failed (e.g.
    a Twilio hiccup) or no number exists yet."""
    if not service.configured:
        raise ResourceNotFoundError("sms_not_configured", "SMS delivery is not configured on this deployment")
    phone_number = service.provision_number_if_needed(business_id)
    return SmsStatusResponse(configured=True, phone_number=phone_number)
