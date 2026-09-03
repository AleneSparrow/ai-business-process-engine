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
already saved. Conversational replies are also written to `integration_outbox`
(`kind=sms_reply`) so `POST /api/v1/internal/integrations/deliver` can retry
a Twilio outage. STOP/START/HELP never enter lead intake.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.domain.models import utc_now

from .sqlalchemy_models import IntegrationOutboxRow, SmsSuppressionRow
from .twilio_client import TwilioAPIError, TwilioClient

if TYPE_CHECKING:
    from .repositories import UnitOfWorkFactory

LOGGER = logging.getLogger("uvicorn.error")

INBOUND_SMS_WEBHOOK_PATH = "/api/v1/public/sms/inbound"
_SMS_REPLY_KIND = "sms_reply"
_MAX_ATTEMPTS = 8
_BACKOFF = timedelta(minutes=5)
_STOP_ACK = (
    "You have been unsubscribed from texts from this number. Reply START to resume."
)
_START_ACK = (
    "You are subscribed to texts from this number again. Reply STOP to opt out."
)
_HELP_ACK = (
    "This number sends updates about your request. Reply STOP to opt out. Reply START to resume."
)


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

    def is_suppressed(self, business_id: str, phone_number: str) -> bool:
        with self.unit_of_work_factory() as uow:
            session = getattr(uow, "session", None)
            if session is None:
                return False
            row = session.get(SmsSuppressionRow, (business_id, phone_number))
            return row is not None

    def opt_out(self, business_id: str, phone_number: str, *, inbound_message_id: str) -> None:
        """Honor STOP: suppress the number, revoke follow-up consent, ack once."""
        try:
            now = utc_now()
            with self.unit_of_work_factory() as uow:
                session = getattr(uow, "session", None)
                if session is not None:
                    existing = session.get(SmsSuppressionRow, (business_id, phone_number))
                    if existing is None:
                        session.add(
                            SmsSuppressionRow(
                                business_id=business_id,
                                phone_number=phone_number,
                                suppressed_at=now,
                            )
                        )
                lead = uow.leads.find_by_identity(business_id, phone_number, None)
                if lead is not None and lead.sms_consent:
                    uow.leads.save(business_id, replace(lead, sms_consent=False), now)
                uow.commit()
            self.enqueue_reply(
                business_id,
                to_number=phone_number,
                body=_STOP_ACK,
                inbound_message_id=inbound_message_id,
                ignore_suppression=True,
            )
        except Exception:  # noqa: BLE001
            LOGGER.exception("sms_opt_out_failed business_id=%s", business_id)

    def opt_in(self, business_id: str, phone_number: str, *, inbound_message_id: str) -> None:
        """Honor START: lift suppression. Does not grant follow-up sms_consent."""
        try:
            with self.unit_of_work_factory() as uow:
                session = getattr(uow, "session", None)
                if session is not None:
                    row = session.get(SmsSuppressionRow, (business_id, phone_number))
                    if row is not None:
                        session.delete(row)
                uow.commit()
            self.enqueue_reply(
                business_id,
                to_number=phone_number,
                body=_START_ACK,
                inbound_message_id=inbound_message_id,
            )
        except Exception:  # noqa: BLE001
            LOGGER.exception("sms_opt_in_failed business_id=%s", business_id)

    def send_help(self, business_id: str, phone_number: str, *, inbound_message_id: str) -> None:
        self.enqueue_reply(
            business_id,
            to_number=phone_number,
            body=_HELP_ACK,
            inbound_message_id=inbound_message_id,
            ignore_suppression=True,
        )

    def enqueue_reply(
        self,
        business_id: str,
        *,
        to_number: str,
        body: str,
        inbound_message_id: str,
        ignore_suppression: bool = False,
    ) -> None:
        """Persist an SMS reply, then try Twilio once. Never raises."""
        try:
            if not ignore_suppression and self.is_suppressed(business_id, to_number):
                return
            now = utc_now()
            outbox_id = f"smsr:{inbound_message_id}"[:128]
            with self.unit_of_work_factory() as uow:
                session = getattr(uow, "session", None)
                if session is None:
                    self.send_outbound(
                        business_id,
                        to_number=to_number,
                        body=body,
                        ignore_suppression=ignore_suppression,
                    )
                    return
                existing = session.get(IntegrationOutboxRow, outbox_id)
                if existing is None:
                    session.add(
                        IntegrationOutboxRow(
                            id=outbox_id,
                            business_id=business_id,
                            kind=_SMS_REPLY_KIND,
                            payload={
                                "to_number": to_number,
                                "body": body,
                                "ignore_suppression": ignore_suppression,
                            },
                            status="PENDING",
                            attempt_count=0,
                            next_attempt_at=now,
                            last_error=None,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    uow.commit()
                elif existing.status != "PENDING":
                    return
            self.deliver_one(outbox_id)
        except Exception:  # noqa: BLE001
            LOGGER.exception(
                "sms_enqueue_failed business_id=%s inbound_message_id=%s",
                business_id,
                inbound_message_id,
            )

    def deliver_due(self, *, limit: int = 50) -> dict[str, int]:
        now = utc_now()
        with self.unit_of_work_factory() as uow:
            session = getattr(uow, "session", None)
            if session is None:
                return {"attempted": 0, "sent": 0, "failed": 0}
            rows = session.scalars(
                select(IntegrationOutboxRow)
                .where(
                    IntegrationOutboxRow.status == "PENDING",
                    IntegrationOutboxRow.kind == _SMS_REPLY_KIND,
                    IntegrationOutboxRow.next_attempt_at <= now,
                )
                .order_by(IntegrationOutboxRow.created_at.asc())
                .limit(limit)
            ).all()
            ids = [row.id for row in rows]
        attempted = sent = failed = 0
        for outbox_id in ids:
            attempted += 1
            if self.deliver_one(outbox_id):
                sent += 1
            else:
                failed += 1
        return {"attempted": attempted, "sent": sent, "failed": failed}

    def deliver_one(self, outbox_id: str) -> bool:
        with self.unit_of_work_factory() as uow:
            session = getattr(uow, "session", None)
            if session is None:
                return False
            row = session.get(IntegrationOutboxRow, outbox_id)
            if row is None or row.status != "PENDING":
                return row is not None and row.status == "SENT"
            payload = dict(row.payload)
            to_number = str(payload.get("to_number") or "")
            body = str(payload.get("body") or "")
            ignore_suppression = bool(payload.get("ignore_suppression"))
            now = utc_now()
            sid = self.send_outbound(
                row.business_id,
                to_number=to_number,
                body=body,
                ignore_suppression=ignore_suppression,
            )
            row.attempt_count += 1
            row.updated_at = now
            if sid:
                row.status = "SENT"
                row.last_error = None
                uow.commit()
                return True
            if row.attempt_count >= _MAX_ATTEMPTS:
                row.status = "FAILED"
                row.last_error = "delivery_exhausted"
            else:
                row.next_attempt_at = now + (_BACKOFF * row.attempt_count)
                row.last_error = "delivery_failed"
            uow.commit()
            return False

    def send_outbound(
        self,
        business_id: str,
        *,
        to_number: str,
        body: str,
        ignore_suppression: bool = False,
    ) -> str | None:
        """Best-effort, never raises. Returns the Twilio message SID on
        success (the durable proof of dispatch a caller can persist for
        outbox-style delivery tracking -- see PersistentFollowUpRunner), or
        None on any failure."""
        if not self.configured:
            return None
        if not ignore_suppression and self.is_suppressed(business_id, to_number):
            LOGGER.info("sms_send_suppressed business_id=%s", business_id)
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
