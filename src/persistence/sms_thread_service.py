"""Staff-visible SMS threads, separate from the anonymous website chat token."""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.conversations import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageDirection,
    MessageRole,
)
from src.domain.models import utc_now
from src.domain.qualification import LeadIntakeResult
from src.domain.states import ProcessState

if TYPE_CHECKING:
    from .repositories import UnitOfWorkFactory

LOGGER = logging.getLogger("uvicorn.error")

SMS_CHANNEL = "sms"
_PAUSED = frozenset(
    {
        ConversationStatus.HUMAN_TAKEOVER_REQUESTED,
        ConversationStatus.HUMAN_TAKEOVER_ACTIVE,
    }
)


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SmsThreadService:
    def __init__(self, unit_of_work_factory: "UnitOfWorkFactory") -> None:
        self.unit_of_work_factory = unit_of_work_factory

    def is_paused(self, business_id: str, phone_number: str) -> bool:
        with self.unit_of_work_factory() as uow:
            conversation = uow.conversations.get_by_channel_session(
                business_id, SMS_CHANNEL, phone_number
            )
        return conversation is not None and conversation.status in _PAUSED

    def append_customer_message(
        self,
        business_id: str,
        phone_number: str,
        *,
        body: str,
        inbound_message_id: str,
    ) -> None:
        """Record an inbound text while a human owns the thread. Never raises."""
        try:
            self._append(
                business_id,
                phone_number,
                body=body,
                inbound_message_id=inbound_message_id,
                intake=None,
            )
        except Exception:  # noqa: BLE001
            LOGGER.exception("sms_thread_append_failed business_id=%s", business_id)

    def sync_from_intake(
        self,
        business_id: str,
        phone_number: str,
        *,
        body: str,
        inbound_message_id: str,
        intake: LeadIntakeResult,
    ) -> None:
        """Mirror an engine turn onto the staff conversation list. Never raises."""
        try:
            self._append(
                business_id,
                phone_number,
                body=body,
                inbound_message_id=inbound_message_id,
                intake=intake,
            )
        except Exception:  # noqa: BLE001
            LOGGER.exception("sms_thread_sync_failed business_id=%s", business_id)

    def _append(
        self,
        business_id: str,
        phone_number: str,
        *,
        body: str,
        inbound_message_id: str,
        intake: LeadIntakeResult | None,
    ) -> None:
        now = utc_now()
        with self.unit_of_work_factory() as uow:
            uow.conversations.lock_session_identity(business_id, SMS_CHANNEL, phone_number)
            conversation = uow.conversations.get_by_channel_session(
                business_id, SMS_CHANNEL, phone_number, for_update=True
            )
            if conversation is None:
                conversation = Conversation(
                    conversation_id=str(uuid4()),
                    business_id=business_id,
                    token_hash=_fingerprint(f"sms-unusable:{business_id}:{phone_number}"),
                    channel=SMS_CHANNEL,
                    status=ConversationStatus.AI_ACTIVE,
                    created_at=now,
                    updated_at=now,
                    last_activity_at=now,
                    token_expires_at=now + timedelta(days=3650),
                    token_revoked_at=now,
                    external_session_id=phone_number,
                )
                uow.conversations.add(conversation)
                session = getattr(uow, "session", None)
                if session is not None:
                    session.flush()
                expected_version = 0
            else:
                expected_version = conversation.version

            if uow.conversation_messages.get_by_external_id(
                business_id, conversation.conversation_id, inbound_message_id
            ):
                return

            sequence = uow.conversation_messages.next_sequence(
                business_id, conversation.conversation_id
            )
            uow.conversation_messages.add(
                ConversationMessage(
                    message_id=str(uuid4()),
                    business_id=business_id,
                    conversation_id=conversation.conversation_id,
                    sequence_number=sequence,
                    direction=MessageDirection.INBOUND,
                    role=MessageRole.CUSTOMER,
                    text=body,
                    created_at=now,
                    external_message_id=inbound_message_id,
                    content_fingerprint=_fingerprint(body),
                )
            )
            if intake is not None:
                conversation.link_case(intake.lead_id, intake.case_id)
                if intake.current_state is ProcessState.NEEDS_HUMAN:
                    conversation.set_status(ConversationStatus.HUMAN_TAKEOVER_REQUESTED, now)
                reply = intake.response.message_text if intake.response is not None else None
                if reply and not intake.duplicate:
                    uow.conversation_messages.add(
                        ConversationMessage(
                            message_id=str(uuid4()),
                            business_id=business_id,
                            conversation_id=conversation.conversation_id,
                            sequence_number=sequence + 1,
                            direction=MessageDirection.OUTBOUND,
                            role=MessageRole.ASSISTANT,
                            text=reply,
                            created_at=now,
                            external_message_id=f"{inbound_message_id}:reply",
                            content_fingerprint=_fingerprint(reply),
                        )
                    )
            conversation.touch(now)
            uow.conversations.save(conversation, expected_version)
            uow.commit()
