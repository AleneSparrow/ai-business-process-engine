"""SMS delivery: per-business Twilio number provisioning and outbound send.

Unlike the CRM webhook (a URL the business owner types in, purely optional),
a business's Twilio number is purchased and configured by this service
itself -- the owner never sees a Twilio dashboard. Provisioning is a
deliberate MANUAL action, not automatic on signup: every provisioned number
is a real ~$1-2/month Twilio charge, so triggering a purchase on every
test/dev signup would be wasteful. Instead, the business owner (or Alena,
during setup) presses "Set up SMS" on the Settings page, which calls
`POST /api/v1/businesses/{business_id}/integrations/sms/provision`.
`provision_number_if_needed` is deliberately best-effort and non-blocking so
it's also safe to retry: it's a no-op if a number already exists, and
returns `None` rather than raising if SMS isn't configured or the purchase
fails for any reason (surfaced to the owner as "Retry" in Settings).

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

    def provision_number_if_needed(self, business_id: str) -> str | None:
        """Idempotent: returns the existing number if one is already
        provisioned, attempts to buy one if SMS is configured and none
        exists yet, or returns None (silently -- this must never raise into
        a signup/onboarding flow) if SMS isn't configured or the purchase
        fails for any reason."""
        existing = self.get_number(business_id)
        if existing is not None:
            return existing
        if not self.configured or not self._public_api_base_url:
            return None
        try:
            client = self._client()
            available = client.find_available_us_number()
            if available is None:
                LOGGER.warning("sms_provision_no_numbers_available business_id=%s", business_id)
                return None
            webhook_url = f"{self._public_api_base_url}{INBOUND_SMS_WEBHOOK_PATH}"
            phone_sid = client.purchase_phone_number(
                phone_number=available, sms_webhook_url=webhook_url
            )
            with self.unit_of_work_factory() as uow:
                # Re-check inside the transaction -- provisioning could race
                # with a concurrent retry from the Settings "retry" action.
                if uow.sms_connections.get_by_business(business_id) is not None:
                    return uow.sms_connections.get_by_business(business_id)[0]  # type: ignore[index]
                uow.sms_connections.add(business_id, available, phone_sid, now=utc_now())
                uow.commit()
            return available
        except TwilioAPIError:
            LOGGER.exception("sms_provision_failed business_id=%s", business_id)
            return None

    def send_outbound(self, business_id: str, *, to_number: str, body: str) -> bool:
        """Best-effort, never raises. Returns whether the send succeeded."""
        if not self.configured:
            return False
        try:
            from_number = self.get_number(business_id)
            if from_number is None:
                LOGGER.warning("sms_send_no_number_configured business_id=%s", business_id)
                return False
            self._client().send_sms(from_number=from_number, to_number=to_number, body=body)
            return True
        except TwilioAPIError:
            LOGGER.exception(
                "sms_send_failed business_id=%s to_number_suffix=%s",
                business_id, to_number[-4:] if len(to_number) >= 4 else "****",
            )
            return False
