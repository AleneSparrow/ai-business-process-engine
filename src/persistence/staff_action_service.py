"""Staff-facing actions on a live conversation/case: reply and resolve.

Both actions require an authenticated staff user scoped to the business (see
`require_own_business` in `src/api/dependencies.py`) -- this service assumes
that check already happened and does not re-derive tenant ownership itself.

"Resolve" does not invent a new transition: NEEDS_HUMAN cases already carry a
`pending_transition` -- the state the deterministic engine wanted to move to
before it needed a human (set by `DecisionRouter._escalation` and consumed by
`ProcessEngine.receive`, see `src/engine/process_engine.py`). Resolving is
just a staff member approving that exact pending transition, submitted as a
`DecisionType.HUMAN` decision with `approved_by` set to their email -- the
same mechanism the engine already validates and audits, not a new one.
"""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from src.domain.auth import StaffUser
from src.domain.conversations import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageDirection,
    MessageRole,
)
from src.domain.events import EventType
from src.domain.models import DecisionType, ProcessCase, ProcessEvent, utc_now
from src.domain.states import ProcessState
from src.engine.decision_router import DecisionRequest
from src.engine.process_engine import ProcessEngine

from .errors import (
    CaseNotAwaitingApprovalError,
    ConversationClosedError,
    ConversationNotLinkedError,
    StaffConversationNotFoundError,
)
from .repositories import UnitOfWork


@dataclass(frozen=True, slots=True)
class StaffActionResult:
    conversation: Conversation
    case: ProcessCase | None


class StaffActionService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        *,
        process_engine: ProcessEngine | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self.process_engine = process_engine or ProcessEngine()

    def reply(
        self,
        business_id: str,
        conversation_id: str,
        staff_user: StaffUser,
        message_text: str,
    ) -> StaffActionResult:
        with self._unit_of_work_factory() as unit_of_work:
            conversation = unit_of_work.conversations.get(business_id, conversation_id, for_update=True)
            if conversation is None:
                raise StaffConversationNotFoundError("Conversation was not found")
            if conversation.status is ConversationStatus.CLOSED:
                raise ConversationClosedError("This conversation is already closed")

            expected_version = conversation.version
            occurred_at = utc_now()
            sequence = unit_of_work.conversation_messages.next_sequence(business_id, conversation_id)
            unit_of_work.conversation_messages.add(ConversationMessage(
                message_id=str(uuid4()),
                business_id=business_id,
                conversation_id=conversation_id,
                sequence_number=sequence,
                direction=MessageDirection.OUTBOUND,
                role=MessageRole.HUMAN,
                text=message_text,
                created_at=occurred_at,
                metadata={"staff_user_id": staff_user.user_id},
            ))
            if conversation.status is ConversationStatus.HUMAN_TAKEOVER_REQUESTED:
                conversation.set_status(ConversationStatus.HUMAN_TAKEOVER_ACTIVE, occurred_at)
            else:
                conversation.touch(occurred_at)
            unit_of_work.conversations.save(conversation, expected_version)

            case = None
            if conversation.case_id is not None:
                case = unit_of_work.cases.get(business_id, conversation.case_id)
                if case is not None:
                    unit_of_work.events.add(business_id, case.case_id, ProcessEvent(
                        EventType.HUMAN_REPLY_SENT,
                        occurred_at=occurred_at,
                        source="staff_action",
                        payload={"staff_user_id": staff_user.user_id, "message_preview": message_text[:200]},
                    ))

            unit_of_work.commit()
            return StaffActionResult(conversation=conversation, case=case)

    def resolve(
        self,
        business_id: str,
        conversation_id: str,
        staff_user: StaffUser,
    ) -> StaffActionResult:
        with self._unit_of_work_factory() as unit_of_work:
            conversation = unit_of_work.conversations.get(business_id, conversation_id, for_update=True)
            if conversation is None:
                raise StaffConversationNotFoundError("Conversation was not found")
            if conversation.case_id is None:
                raise ConversationNotLinkedError("This conversation isn't linked to a case yet")

            case = unit_of_work.cases.get(business_id, conversation.case_id)
            if case is None:
                raise ConversationNotLinkedError("The linked case was not found")
            if case.current_state is not ProcessState.NEEDS_HUMAN or case.pending_transition is None:
                raise CaseNotAwaitingApprovalError(
                    "This case isn't waiting on human approval right now"
                )

            occurred_at = utc_now()
            expected_case_version = case.version
            existing_event_count = len(case.event_history)
            event = ProcessEvent(
                EventType.TRIGGER_RECEIVED,
                occurred_at=occurred_at,
                source="staff_action",
                payload={"action": "resolve", "staff_user_id": staff_user.user_id},
            )
            request = DecisionRequest(
                DecisionType.HUMAN,
                case.pending_transition,
                approved_by=staff_user.email,
            )
            self.process_engine.receive(case, event, request)
            unit_of_work.cases.save(case, expected_case_version)
            unit_of_work.events.add_many(
                business_id, case.case_id, case.event_history[existing_event_count:]
            )

            if conversation.status is not ConversationStatus.CLOSED:
                expected_conversation_version = conversation.version
                conversation.set_status(ConversationStatus.CLOSED, occurred_at)
                unit_of_work.conversations.save(conversation, expected_conversation_version)

            unit_of_work.commit()
            return StaffActionResult(conversation=conversation, case=case)

    def record_escalation_feedback(
        self,
        business_id: str,
        conversation_id: str,
        staff_user: StaffUser,
        outcome: str,
    ) -> StaffActionResult:
        """Record a staff label without storing customer text or free-form PII."""
        allowed = {
            "unnecessary",
            "missed",
            "wrong_service",
            "identity_same_customer",
            "identity_different_customer",
        }
        if outcome not in allowed:
            raise ValueError("unsupported escalation feedback outcome")
        with self._unit_of_work_factory() as unit_of_work:
            conversation = unit_of_work.conversations.get(
                business_id, conversation_id, for_update=True
            )
            if conversation is None:
                raise StaffConversationNotFoundError("Conversation was not found")
            if conversation.case_id is None:
                raise ConversationNotLinkedError("This conversation isn't linked to a case yet")
            case = unit_of_work.cases.get(business_id, conversation.case_id)
            if case is None:
                raise ConversationNotLinkedError("The linked case was not found")
            unit_of_work.events.add(
                business_id,
                case.case_id,
                ProcessEvent(
                    EventType.ESCALATION_FEEDBACK_RECORDED,
                    occurred_at=utc_now(),
                    source="staff_action",
                    payload={
                        "outcome": outcome,
                        "staff_user_id": staff_user.user_id,
                    },
                ),
            )
            unit_of_work.commit()
            return StaffActionResult(conversation=conversation, case=case)
