"""SMS delivery: per-business Twilio number provisioning and outbound send.

Unlike the CRM webhook (a URL the business owner types in, purely optional),
a business's Twilio number is purchased and configured by this service
itself -- the owner never sees a Twilio dashboard. Provisioning is a
deliberate MANUAL action, not automatic on signup: every provisioned number
is a real ~$1-2/month Twilio charge, so triggering a purchase on every
test/dev signup would be wasteful. Instead, the business owner (or Alena,
during setup) presses "Set up SMS" on the Settings page, which calls
`POST /api/v1/businesses/{business_id}/integrations/sms/provision`.

`provision_number_if_needed` is a no-op (returns the existing number) if one
is already provisioned, but RAISES `SmsProvisioningError` with a specific,
human-readable reason if it isn't and the attempt fails -- unlike
`send_outbound` below, this has exactly one caller (that manual "Set up SMS"
button), not a non-blocking background path, so there's nothing to protect
by swallowing the failure. A silent no-op here previously just looked like
the button doing nothing at all; the caller (src/api/routes/sms.py) turns
this into a real error message the owner actually sees.

`send_outbound` is also never-raising for the same reason `CrmWebhookService`
isn't: it's called from inside the inbound-SMS webhook handler, right after
the lead-intake transaction has already committed -- a delivery failure here
must not turn into a 500 back to Twilio or retroactively undo work that's
already saved.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.models import utc_now

from .twilio_client import TwilioAPIError, TwilioClient

if TYPE_CHECKING:
    from .repositories import UnitOfWorkFactory

LOGGER = logging.getLogger("uvicorn.error")

INBOUND_SMS_WEBHOOK_PATH = "/api/v1/public/sms/inbound"


class SmsProvisioningError(RuntimeError):
    """Raised by `provision_number_if_needed` with a human-readable reason
    when it can't hand back a number -- see that method's docstring for why
    this is fine to raise (unlike the rest of this service)."""


class SmsService:
    def __init__(
        self,
        unit_of_work_factory: "UnitOfWorkFactory",
        *,
        account_sid: str | None,
        auth_token: str | None,
        public_api_base_url: str | None,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._public_api_base_url = public_api_base_url

    @property
    def configured(self) -> bool:
        return self._account_sid is not None and self._auth_token is not None

    def _client(self) -> TwilioClient:
        assert self._account_sid is not None and self._auth_token is not None
        return TwilioClient(self._account_sid, self._auth_token)

    def get_number(self, business_id: str) -> str | None:
        with self.unit_of_work_factory() as uow:
            connection = uow.sms_connections.get_by_business(business_id)
        return connection[0] if connection else None

    def resolve_business_id_by_phone(self, phone_number: str) -> str | None:
        with self.unit_of_work_factory() as uow:
            return uow.sms_connections.get_business_id_by_phone(phone_number)

    def provision_number_if_needed(self, business_id: str) -> str:
        """Idempotent: returns the existing number if one is already
        provisioned, otherwise attempts to buy one. Raises
        `SmsProvisioningError` with a specific reason on any failure -- see
        the module docstring for why that's the right behavior here."""
        existing = self.get_number(business_id)
        if existing is not None:
            return existing
        if not self.configured:
            raise SmsProvisioningError("SMS delivery is not configured on this deployment.")
        if not self._public_api_base_url:
            raise SmsProvisioningError(
                "PUBLIC_API_BASE_URL is not set on this deployment, so a purchased number "
                "would have nowhere to point its inbound webhook."
            )
        try:
            client = self._client()
            available = client.find_available_us_number()
        except TwilioAPIError as exc:
            LOGGER.exception("sms_provision_search_failed business_id=%s", business_id)
            raise SmsProvisioningError(f"Twilio couldn't search for a number: {exc}") from exc
        if available is None:
            LOGGER.warning("sms_provision_no_numbers_available business_id=%s", business_id)
            raise SmsProvisioningError(
                "Twilio has no available US phone numbers right now -- this can happen on a "
                "trial account. Try again shortly, or check the Twilio Console for restrictions."
            )
        webhook_url = f"{self._public_api_base_url}{INBOUND_SMS_WEBHOOK_PATH}"
        try:
            phone_sid = client.purchase_phone_number(
                phone_number=available, sms_webhook_url=webhook_url
            )
        except TwilioAPIError as exc:
            LOGGER.exception("sms_provision_purchase_failed business_id=%s", business_id)
            raise SmsProvisioningError(f"Twilio couldn't complete the purchase: {exc}") from exc
        with self.unit_of_work_factory() as uow:
            # Re-check inside the transaction -- provisioning could race
            # with a concurrent retry from the Settings "Set up SMS" button.
            existing_race = uow.sms_connections.get_by_business(business_id)
            if existing_race is not None:
                return existing_race[0]
            uow.sms_connections.add(business_id, available, phone_sid, now=utc_now())
            uow.commit()
        return available

    def send_outbound(self, business_id: str, *, to_number: str, body: str) -> str | None:
        """Best-effort, never raises. Returns the Twilio message SID on
        success (the durable proof of dispatch a caller can persist for
        outbox-style delivery tracking -- see PersistentFollowUpRunner), or
        None on any failure."""
        if not self.configured:
            return None
        try:
            from_number = self.get_number(business_id)
            if from_number is None:
                LOGGER.warning("sms_send_no_number_configured business_id=%s", business_id)
                return None
            return self._client().send_sms(from_number=from_number, to_number=to_number, body=body)
        except TwilioAPIError:
            LOGGER.exception(
                "sms_send_failed business_id=%s to_number_suffix=%s",
                business_id, to_number[-4:] if len(to_number) >= 4 else "****",
            )
            return None
