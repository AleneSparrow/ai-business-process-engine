"""CRM webhook configuration and best-effort delivery (e.g. a Clio/Zapier/
Make catch hook, configured per business).

The URL lives in its own table (`crm_webhook_connections`), not Business
DNA -- see `CrmWebhookConnectionRow` for why. Delivery never raises and never
blocks: a CRM sync failure must not surface to the customer or affect the
lead-to-sale flow it's reporting on. Call `notify` only *after* the state
transition it reports has already committed -- see its call sites in
`src/api/routes/public_conversations.py`, not from inside the transactional
engine/persistence layer itself.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.models import utc_now

from .crm_webhook_client import post_json

if TYPE_CHECKING:
    from .repositories import UnitOfWorkFactory

LOGGER = logging.getLogger("uvicorn.error")

# States worth telling a CRM about -- a lead worth following up on, or a won
# deal. Deliberately not every state (e.g. NEEDS_HUMAN, LOST) to keep this a
# simple, predictable v1; widen this set later if a real Clio integration
# needs more granularity.
NOTIFIABLE_STATES = frozenset({"QUALIFIED", "WON"})


class CrmWebhookService:
    def __init__(self, unit_of_work_factory: "UnitOfWorkFactory") -> None:
        self.unit_of_work_factory = unit_of_work_factory

    def configure(self, business_id: str, webhook_url: str) -> None:
        webhook_url = webhook_url.strip()
        if not webhook_url:
            raise ValueError("webhook_url must not be empty")
        if not webhook_url.startswith(("https://", "http://")):
            raise ValueError("webhook_url must be an http(s) URL")
        with self.unit_of_work_factory() as uow:
            uow.crm_webhook_connections.upsert(business_id, webhook_url, now=utc_now())
            uow.commit()

    def remove(self, business_id: str) -> None:
        with self.unit_of_work_factory() as uow:
            uow.crm_webhook_connections.delete(business_id)
            uow.commit()

    def is_configured(self, business_id: str) -> bool:
        with self.unit_of_work_factory() as uow:
            return uow.crm_webhook_connections.get_url(business_id) is not None

    def notify_if_configured(self, business_id: str, *, conversation_id: str, state: str) -> None:
        """Best-effort, never raises. Only fires for `NOTIFIABLE_STATES`.

        Keyed by conversation_id (not case_id/lead_id) deliberately -- the
        public conversation API this is called from doesn't expose internal
        case/lead identifiers to that layer, and conversation_id is enough
        for a v1 "resync this case" ping. Widen the payload later if a real
        Clio integration needs the full case detail inline."""
        if state not in NOTIFIABLE_STATES:
            return
        try:
            with self.unit_of_work_factory() as uow:
                url = uow.crm_webhook_connections.get_url(business_id)
            if url is None:
                return
            delivered = post_json(url, {
                "business_id": business_id,
                "conversation_id": conversation_id,
                "state": state,
                "occurred_at": utc_now().isoformat(),
            })
            if not delivered:
                LOGGER.warning(
                    "crm_webhook_delivery_failed business_id=%s conversation_id=%s state=%s",
                    business_id, conversation_id, state,
                )
        except Exception:  # noqa: BLE001 -- best-effort by design, see module docstring
            LOGGER.exception(
                "crm_webhook_notify_error business_id=%s conversation_id=%s state=%s",
                business_id, conversation_id, state,
            )
