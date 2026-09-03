"""CRM webhook configuration and outbox-backed delivery."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import select

from src.domain.models import utc_now

from .crm_webhook_client import post_json
from .sqlalchemy_models import IntegrationOutboxRow
from .webhook_url_security import validate_public_https_url

if TYPE_CHECKING:
    from .repositories import UnitOfWorkFactory

LOGGER = logging.getLogger("uvicorn.error")
NOTIFIABLE_STATES = frozenset({"QUALIFIED", "WON"})
_MAX_ATTEMPTS = 8
_BACKOFF = timedelta(minutes=5)


class CrmWebhookService:
    def __init__(
        self,
        unit_of_work_factory: "UnitOfWorkFactory",
        *,
        url_validator: Callable[[str], None] = validate_public_https_url,
        webhook_poster: Callable[[str, dict[str, object]], bool] = post_json,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self._url_validator = url_validator
        self._webhook_poster = webhook_poster

    def configure(self, business_id: str, webhook_url: str) -> None:
        webhook_url = webhook_url.strip()
        self._url_validator(webhook_url)
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
        """Enqueue a durable outbox row, then attempt one immediate delivery.

        Never raises. A crash after commit and before HTTP still leaves a
        PENDING row for POST /api/v1/internal/integrations/deliver.
        """
        if state not in NOTIFIABLE_STATES:
            return
        try:
            now = utc_now()
            payload = {
                "business_id": business_id,
                "conversation_id": conversation_id,
                "state": state,
                "occurred_at": now.isoformat(),
            }
            with self.unit_of_work_factory() as uow:
                url = uow.crm_webhook_connections.get_url(business_id)
                if url is None:
                    return
                session = getattr(uow, "session", None)
                if session is None:
                    return
                row = IntegrationOutboxRow(
                    id=str(uuid4()),
                    business_id=business_id,
                    kind="crm_webhook",
                    payload=payload,
                    status="PENDING",
                    attempt_count=0,
                    next_attempt_at=now,
                    last_error=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                uow.commit()
                outbox_id = row.id
            self.deliver_one(outbox_id)
        except Exception:  # noqa: BLE001
            LOGGER.exception(
                "crm_webhook_notify_error business_id=%s conversation_id=%s state=%s",
                business_id, conversation_id, state,
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
                    IntegrationOutboxRow.kind == "crm_webhook",
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
            url = uow.crm_webhook_connections.get_url(row.business_id)
            payload: dict[str, Any] = dict(row.payload)
            now = utc_now()
            if url is None:
                row.status = "FAILED"
                row.last_error = "webhook_not_configured"
                row.updated_at = now
                uow.commit()
                return False
            try:
                self._url_validator(url)
                delivered = self._webhook_poster(url, payload)
            except Exception as exc:  # noqa: BLE001
                delivered = False
                LOGGER.warning(
                    "crm_webhook_delivery_failed outbox_id=%s error=%s",
                    outbox_id,
                    type(exc).__name__,
                )
            row.attempt_count += 1
            row.updated_at = now
            if delivered:
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
