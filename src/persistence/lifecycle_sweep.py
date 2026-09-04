"""Advance finished bookings through PAID → COMPLETED → REVIEW_REQUESTED.

Staff can do the same actions from the dashboard; this sweep closes the loop
when the booked appointment time has passed and payment is already settled
(or was never required). It never invents a payment.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from src.domain.commercial import BookingStatus, CommercialResponse, PaymentStatus, PaymentType
from src.domain.conversations import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageDirection,
    MessageRole,
)
from src.domain.states import ProcessState
from src.persistence.sqlalchemy_models import BookingRow

from .commercial_service import CommercialWorkflowService

if TYPE_CHECKING:
    from .repositories import UnitOfWork, UnitOfWorkFactory
    from .sms_service import SmsService


class LifecycleSweep:
    def __init__(
        self,
        unit_of_work_factory: "UnitOfWorkFactory",
        *,
        sms_service: "SmsService | None" = None,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.commercial = CommercialWorkflowService()
        self.sms_service = sms_service

    def run(self, now: datetime, *, limit: int = 200) -> dict[str, int]:
        with self.unit_of_work_factory() as uow:
            session = getattr(uow, "session", None)
            if session is None:
                return {"cases_scanned": 0, "completed": 0, "reviews_requested": 0}
            rows = session.execute(
                select(BookingRow.business_id, BookingRow.case_id)
                .where(
                    BookingRow.status.in_(
                        [BookingStatus.CONFIRMED.value, BookingStatus.RESCHEDULED.value]
                    ),
                    BookingRow.end_at <= now,
                )
                .limit(limit)
            ).all()
        completed = 0
        reviews = 0
        scanned = 0
        pending_sms: list[tuple[Conversation, str, str]] = []
        for business_id, case_id in rows:
            with self.unit_of_work_factory() as uow:
                case = uow.cases.get(business_id, case_id)
                if case is None:
                    continue
                scanned += 1
                dna_version = uow.business_dna.get_active(business_id)
                dna = dna_version.configuration if dna_version is not None else {}
                conversation = self._linked_conversation(uow, case.business_id, case.case_id)
                expected_version = conversation.version if conversation is not None else None
                outbound: list[tuple[str, CommercialResponse]] = []
                if case.current_state is ProcessState.BOOKED:
                    self.commercial._close_commercial_win(uow, case, now)
                elif case.current_state is ProcessState.FOLLOW_UP:
                    self.commercial.complete_win_if_ready(uow, case, occurred_at=now)
                if case.current_state is ProcessState.WON:
                    payment = uow.payment_requests.get_for_case_type(
                        business_id, case_id, PaymentType.DEPOSIT
                    ) or uow.payment_requests.get_for_case_type(
                        business_id, case_id, PaymentType.FINAL
                    )
                    if payment is None or payment.status is PaymentStatus.PAID:
                        outbound.append((
                            "mark_completed",
                            self.commercial.mark_service_completed(
                                uow, case, occurred_at=now, recorded_by="lifecycle_sweep"
                            ),
                        ))
                        completed += 1
                if case.current_state is ProcessState.PAID:
                    outbound.append((
                        "mark_completed",
                        self.commercial.mark_service_completed(
                            uow, case, occurred_at=now, recorded_by="lifecycle_sweep"
                        ),
                    ))
                    completed += 1
                if case.current_state is ProcessState.COMPLETED:
                    outbound.append((
                        "request_review",
                        self.commercial.request_review(
                            uow, case, dna, occurred_at=now, recorded_by="lifecycle_sweep"
                        ),
                    ))
                    reviews += 1
                if conversation is not None:
                    for action, response in outbound:
                        self._append_outbound(uow, conversation, response, now, action)
                        pending_sms.append((conversation, response.message_text, action))
                    if outbound:
                        conversation.metadata["current_state"] = case.current_state.value
                        if conversation.status in {
                            ConversationStatus.HUMAN_TAKEOVER_REQUESTED,
                            ConversationStatus.HUMAN_TAKEOVER_ACTIVE,
                            ConversationStatus.CLOSED,
                        }:
                            conversation.set_status(ConversationStatus.AI_ACTIVE, now)
                        else:
                            conversation.touch(now)
                        uow.conversations.save(conversation, expected_version)
                uow.commit()
        self._deliver_sms(pending_sms)
        return {
            "cases_scanned": scanned,
            "completed": completed,
            "reviews_requested": reviews,
        }

    def _linked_conversation(
        self,
        uow: "UnitOfWork",
        business_id: str,
        case_id: str,
    ) -> Conversation | None:
        conversations = uow.conversations.list_for_case(business_id, case_id)
        if not conversations:
            return None
        return uow.conversations.get(
            business_id, conversations[0].conversation_id, for_update=True
        )

    def _append_outbound(
        self,
        uow: "UnitOfWork",
        conversation: Conversation,
        response: CommercialResponse,
        occurred_at: datetime,
        action: str,
    ) -> None:
        sequence = uow.conversation_messages.next_sequence(
            conversation.business_id, conversation.conversation_id
        )
        uow.conversation_messages.add(ConversationMessage(
            message_id=str(uuid4()),
            business_id=conversation.business_id,
            conversation_id=conversation.conversation_id,
            sequence_number=sequence,
            direction=MessageDirection.OUTBOUND,
            role=MessageRole.ASSISTANT,
            text=response.message_text,
            created_at=occurred_at,
            metadata={"reason": response.reason, "lifecycle_action": action},
        ))

    def _deliver_sms(self, pending: list[tuple[Conversation, str, str]]) -> None:
        if self.sms_service is None:
            return
        for conversation, body, action in pending:
            if conversation.channel != "sms" or not conversation.external_session_id or not body:
                continue
            self.sms_service.enqueue_reply(
                conversation.business_id,
                to_number=conversation.external_session_id,
                body=body,
                inbound_message_id=f"lifecycle:{conversation.conversation_id}:{action}",
            )
