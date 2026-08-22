"""Transactional, tenant-scoped orchestration for anonymous website conversations."""

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import uuid4

from src.domain.conversations import (
    Conversation,
    ConversationContext,
    ConversationContextMessage,
    ConversationMessage,
    ConversationStatus,
    MessageDirection,
    MessageRole,
)
from src.domain.events import EventType
from src.domain.models import DecisionType, ProcessEvent, utc_now
from src.domain.commercial import BookingStatus, PaymentStatus, PaymentType, QuoteStatus
from src.domain.qualification import IncomingMessage, LeadIntakeResult
from src.domain.states import ProcessState
from src.engine.customer_response_generator import CustomerResponseGenerator
from src.engine.decision_router import DecisionRequest
from src.engine.intent_extractor import IntentExtractor
from src.engine.question_generator import QuestionGenerator
from src.engine.reassurance_response_generator import (
    ReassuranceResponseGenerator,
    UniversalReassuranceResponseGenerator,
)

from .commercial_service import CommercialWorkflowService
from .errors import (
    ConversationTokenError,
    ConversationTokenExpiredError,
    IdempotencyCollisionError,
    MessageScopeError,
)
from .lead_intake import PersistentLeadIntakeService
from .repositories import UnitOfWork, UnitOfWorkFactory


_EMAIL = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{5,}\d)(?!\w)")
_TERMINAL_CASE_STATES = frozenset({
    ProcessState.LOST,
    ProcessState.CANCELLED,
    ProcessState.PAID,
    ProcessState.COMPLETED,
})
_AUTONOMOUS_CASE_STATES = frozenset({
    ProcessState.NEW_LEAD,
    ProcessState.CONTACTED,
    ProcessState.QUALIFYING,
    ProcessState.QUALIFIED,
    ProcessState.QUOTED,
    ProcessState.BOOKED,
    ProcessState.WON,
})


@dataclass(frozen=True, slots=True)
class PublicConversationMessage:
    direction: MessageDirection
    role: MessageRole
    text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PublicConversation:
    internal_conversation_id: str
    conversation_token: str
    status: ConversationStatus
    current_state: ProcessState | None
    requires_human: bool
    messages: tuple[PublicConversationMessage, ...]
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class PublicBooking:
    booking_id: str
    service_id: str
    status: BookingStatus
    start_at: datetime
    end_at: datetime
    timezone: str


@dataclass(frozen=True, slots=True)
class PublicQuote:
    quote_id: str
    service_id: str
    status: QuoteStatus
    currency: str
    total: Decimal
    valid_until: datetime


@dataclass(frozen=True, slots=True)
class PublicPaymentRequest:
    payment_request_id: str
    status: PaymentStatus
    payment_type: PaymentType
    amount: Decimal
    currency: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class PublicProposedSlot:
    # 1-based -- matches exactly what DeterministicSlotPreferenceInterpreter
    # accepts as a numeric reply ("1", "2", ...), so a widget can send this
    # value straight back as the customer's message when a slot button is
    # clicked, with zero backend changes needed.
    option: int
    slot_id: str
    start_at: datetime
    end_at: datetime
    timezone: str


@dataclass(frozen=True, slots=True)
class PublicCommercialSnapshot:
    current_state: ProcessState | None
    booking: PublicBooking | None
    quote: PublicQuote | None
    payment_request: PublicPaymentRequest | None
    proposed_slots: tuple[PublicProposedSlot, ...] = ()


class ConversationService:
    """Persists the conversation and existing intake workflow in one transaction."""

    CHANNEL = "webchat"
    CONTEXT_MESSAGE_LIMIT = 8
    PUBLIC_HISTORY_LIMIT = 100
    # A LOST case used to be a permanent dead end -- every message after it
    # got the same static qualification.lost_message forever, even a
    # customer correcting an obvious mistake ("sorry, typo, it's actually
    # 90210"). Bounded per conversation (not unlimited) so someone
    # repeatedly messaging a genuinely out-of-scope, correctly-closed
    # conversation can't trigger unbounded AI intent-extraction calls --
    # same bounded-retry shape as AnthropicProvider._MAX_STRUCTURED_OUTPUT_ATTEMPTS.
    MAX_REACTIVATION_ATTEMPTS = 3

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        intent_extractor: IntentExtractor,
        question_generator: QuestionGenerator,
        customer_response_generator: CustomerResponseGenerator,
        *,
        reassurance_response_generator: ReassuranceResponseGenerator | None = None,
        universal_reassurance_response_generator: UniversalReassuranceResponseGenerator | None = None,
        token_ttl_hours: int = 720,
    ) -> None:
        if not 1 <= token_ttl_hours <= 8_760:
            raise ValueError("conversation token TTL must be between 1 and 8760 hours")
        self.unit_of_work_factory = unit_of_work_factory
        self.intake = PersistentLeadIntakeService(
            unit_of_work_factory,
            intent_extractor,
            question_generator,
            customer_response_generator=customer_response_generator,
            reassurance_response_generator=reassurance_response_generator,
            universal_reassurance_response_generator=universal_reassurance_response_generator,
        )
        self.commercial = CommercialWorkflowService()
        self.token_ttl = timedelta(hours=token_ttl_hours)

    def create(
        self,
        business_id: str,
        *,
        message_text: str | None = None,
        external_message_id: str | None = None,
        correlation_id: str | None = None,
        conversation_token: str | None = None,
        sms_consent: bool = False,
    ) -> PublicConversation:
        if (message_text is None) != (external_message_id is None):
            raise ValueError("message_text and external_message_id must be supplied together")
        token = conversation_token or secrets.token_urlsafe(32)
        if conversation_token is not None:
            self._validate_new_token(conversation_token)
        token_hash = self.hash_token(token)
        with self.unit_of_work_factory() as uow:
            dna = self._active_dna(uow, business_id)
            self._ensure_public_chat_enabled(dna)
            uow.conversations.lock_token_identity(business_id, token_hash)
            existing = uow.conversations.get_by_token_hash(
                business_id, token_hash, for_update=True
            )
            if existing is not None:
                self._validate_conversation_token(existing)
                prior = uow.conversation_messages.list_for_conversation(
                    business_id, existing.conversation_id, limit=1
                )
                if message_text is not None and external_message_id is not None:
                    matching = uow.conversation_messages.get_by_external_id(
                        business_id, existing.conversation_id, external_message_id
                    )
                    if matching is None and prior:
                        raise IdempotencyCollisionError(
                            "conversation create token was reused for a different first message"
                        )
                    duplicate = self._process_message(
                        uow,
                        existing,
                        message_text,
                        external_message_id,
                        correlation_id,
                        dna,
                        save_conversation=True,
                        sms_consent=sms_consent,
                    )
                else:
                    duplicate = True
                snapshot = self._snapshot(uow, existing, token, duplicate=duplicate)
                uow.commit()
                return snapshot

            now = utc_now()
            conversation = Conversation(
                conversation_id=str(uuid4()),
                business_id=business_id,
                token_hash=token_hash,
                channel=self.CHANNEL,
                status=ConversationStatus.AI_ACTIVE,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
                token_expires_at=now + self.token_ttl,
            )
            uow.conversations.add(conversation)
            duplicate = False
            if message_text is not None and external_message_id is not None:
                duplicate = self._process_message(
                    uow,
                    conversation,
                    message_text,
                    external_message_id,
                    correlation_id,
                    dna,
                    save_conversation=True,
                    sms_consent=sms_consent,
                )
            snapshot = self._snapshot(uow, conversation, token, duplicate=duplicate)
            uow.commit()
            return snapshot

    def send_message(
        self,
        business_id: str,
        conversation_token: str,
        *,
        message_text: str,
        external_message_id: str,
        correlation_id: str | None = None,
        sms_consent: bool = False,
    ) -> PublicConversation:
        token_hash = self.hash_token(conversation_token)
        with self.unit_of_work_factory() as uow:
            uow.conversations.lock_token_identity(business_id, token_hash)
            conversation = uow.conversations.get_by_token_hash(
                business_id, token_hash, for_update=True
            )
            self._validate_conversation_token(conversation)
            assert conversation is not None
            dna = self._active_dna(uow, business_id)
            self._ensure_public_chat_enabled(dna)
            duplicate = self._process_message(
                uow,
                conversation,
                message_text,
                external_message_id,
                correlation_id,
                dna,
                save_conversation=True,
                sms_consent=sms_consent,
            )
            snapshot = self._snapshot(
                uow, conversation, conversation_token, duplicate=duplicate
            )
            uow.commit()
            return snapshot

    def get(
        self,
        business_id: str,
        conversation_token: str,
    ) -> PublicConversation:
        with self.unit_of_work_factory() as uow:
            conversation = uow.conversations.get_by_token_hash(
                business_id, self.hash_token(conversation_token)
            )
            self._validate_conversation_token(conversation)
            assert conversation is not None
            return self._snapshot(uow, conversation, conversation_token)

    def get_commercial(
        self,
        business_id: str,
        conversation_token: str,
    ) -> PublicCommercialSnapshot:
        """Return only commercial data owned by the token-bound tenant conversation."""
        with self.unit_of_work_factory() as uow:
            conversation = uow.conversations.get_by_token_hash(
                business_id, self.hash_token(conversation_token), for_update=True
            )
            self._validate_conversation_token(conversation)
            assert conversation is not None
            if conversation.case_id is None:
                return PublicCommercialSnapshot(None, None, None, None)
            case = uow.cases.get(business_id, conversation.case_id)
            if case is None or case.lead.lead_id != conversation.lead_id:
                raise RuntimeError("conversation references an invalid tenant case")
            occurred_at = utc_now()
            self.commercial.expire_due_items(uow, case, occurred_at=occurred_at)
            case = uow.cases.get(business_id, conversation.case_id)
            if case is None or case.lead.lead_id != conversation.lead_id:
                raise RuntimeError("commercial expiration invalidated the tenant case")
            proposed_slots = tuple(
                PublicProposedSlot(index, slot.slot_id, slot.start_at, slot.end_at, slot.timezone)
                for index, slot in enumerate(
                    self.commercial.get_proposed_slots(
                        conversation.metadata, occurred_at=occurred_at
                    ),
                    start=1
                )
            )
            booking = uow.bookings.get_for_case(business_id, case.case_id)
            quote = uow.quotes.get_for_case(business_id, case.case_id)
            payment = uow.payment_requests.get_for_case_type(
                business_id, case.case_id, PaymentType.DEPOSIT
            ) or uow.payment_requests.get_for_case_type(
                business_id, case.case_id, PaymentType.FINAL
            )
            result = PublicCommercialSnapshot(
                case.current_state,
                None if booking is None else PublicBooking(
                    booking.booking_id,
                    booking.service_id,
                    booking.status,
                    booking.start_at,
                    booking.end_at,
                    booking.timezone,
                ),
                None if quote is None else PublicQuote(
                    quote.quote_id,
                    quote.service_id,
                    quote.status,
                    quote.currency,
                    quote.total,
                    quote.valid_until,
                ),
                None if payment is None else PublicPaymentRequest(
                    payment.payment_request_id,
                    payment.status,
                    payment.payment_type,
                    payment.amount,
                    payment.currency,
                    payment.expires_at,
                ),
                proposed_slots,
            )
            uow.commit()
            return result

    def _process_message(
        self,
        uow: UnitOfWork,
        conversation: Conversation,
        message_text: str,
        external_message_id: str,
        correlation_id: str | None,
        dna: Mapping[str, Any],
        *,
        save_conversation: bool,
        sms_consent: bool = False,
    ) -> bool:
        fingerprint = hashlib.sha256(message_text.encode("utf-8")).hexdigest()
        existing = uow.conversation_messages.get_by_external_id(
            conversation.business_id,
            conversation.conversation_id,
            external_message_id,
        )
        if existing is not None:
            if existing.content_fingerprint != fingerprint:
                raise IdempotencyCollisionError(
                    "conversation message identity was reused with different content"
                )
            return True

        expected_version = conversation.version
        occurred_at = utc_now()
        self._synchronize_case_status(uow, conversation, occurred_at)
        sequence = uow.conversation_messages.next_sequence(
            conversation.business_id, conversation.conversation_id
        )
        prior_messages = uow.conversation_messages.list_for_conversation(
            conversation.business_id,
            conversation.conversation_id,
            limit=self.CONTEXT_MESSAGE_LIMIT,
        )
        uow.conversation_messages.add(ConversationMessage(
            message_id=str(uuid4()),
            business_id=conversation.business_id,
            conversation_id=conversation.conversation_id,
            sequence_number=sequence,
            direction=MessageDirection.INBOUND,
            role=MessageRole.CUSTOMER,
            text=message_text,
            created_at=occurred_at,
            external_message_id=external_message_id,
            content_fingerprint=fingerprint,
            correlation_id=correlation_id,
        ))

        self._maybe_reactivate_lost_case(uow, conversation, occurred_at)

        if conversation.status is ConversationStatus.AI_ACTIVE:
            case = (
                uow.cases.get(conversation.business_id, conversation.case_id)
                if conversation.case_id is not None
                else None
            )
            if case is not None and case.current_state in {
                ProcessState.QUALIFIED,
                ProcessState.QUOTED,
                ProcessState.BOOKED,
                ProcessState.WON,
            }:
                commercial_response = self.commercial.handle_message(
                    uow,
                    case,
                    dna,
                    conversation.metadata,
                    message_text,
                    occurred_at=occurred_at,
                )
                response_text = commercial_response.message_text
                response_reason = commercial_response.reason
                current_state = case.current_state
                conversation.metadata["unresolved_items"] = []
            else:
                result = self._run_intake(
                    uow,
                    conversation,
                    message_text,
                    external_message_id,
                    occurred_at,
                    prior_messages,
                    sms_consent=sms_consent,
                )
                conversation.link_case(result.lead_id, result.case_id)
                response_text, response_reason = self._response_for_result(result, dna)
                current_state = result.current_state
                conversation.metadata["unresolved_items"] = list(
                    self._unresolved_items(result, dna)
                )
                self._track_questions(conversation, result, dna, occurred_at)
                if current_state is ProcessState.QUALIFIED:
                    case = uow.cases.get(conversation.business_id, result.case_id)
                    if case is None:
                        raise RuntimeError("qualified intake result references a missing case")
                    commercial_response = self.commercial.initialize(
                        uow,
                        case,
                        dna,
                        conversation.metadata,
                        occurred_at=occurred_at,
                    )
                    response_text = commercial_response.message_text
                    response_reason = commercial_response.reason
                    current_state = case.current_state
                    conversation.metadata["unresolved_items"] = []
            conversation.metadata["current_state"] = current_state.value
            if current_state is ProcessState.NEEDS_HUMAN:
                conversation.set_status(
                    ConversationStatus.HUMAN_TAKEOVER_REQUESTED, occurred_at
                )
            elif current_state in _TERMINAL_CASE_STATES:
                conversation.set_status(ConversationStatus.CLOSED, occurred_at)
        else:
            response_text, response_reason = self._paused_response(conversation, dna)
            current_state = self._stored_state(conversation)

        outbound_time = utc_now()
        uow.conversation_messages.add(ConversationMessage(
            message_id=str(uuid4()),
            business_id=conversation.business_id,
            conversation_id=conversation.conversation_id,
            sequence_number=sequence + 1,
            direction=MessageDirection.OUTBOUND,
            role=MessageRole.ASSISTANT,
            text=response_text,
            created_at=outbound_time,
            correlation_id=correlation_id,
            metadata={
                "reason": response_reason,
                "requires_human": conversation.status in {
                    ConversationStatus.HUMAN_TAKEOVER_REQUESTED,
                    ConversationStatus.HUMAN_TAKEOVER_ACTIVE,
                },
                "resulting_state": current_state.value if current_state else None,
            },
        ))
        conversation.touch(outbound_time)
        if save_conversation:
            uow.conversations.save(conversation, expected_version)
        return False

    @staticmethod
    def _synchronize_case_status(
        uow: UnitOfWork,
        conversation: Conversation,
        occurred_at: datetime,
    ) -> None:
        if conversation.status is not ConversationStatus.AI_ACTIVE or conversation.case_id is None:
            return
        case = uow.cases.get(conversation.business_id, conversation.case_id)
        if case is None or case.lead.lead_id != conversation.lead_id:
            raise RuntimeError("conversation references an invalid tenant case")
        conversation.metadata["current_state"] = case.current_state.value
        if case.current_state is ProcessState.NEEDS_HUMAN:
            conversation.set_status(
                ConversationStatus.HUMAN_TAKEOVER_REQUESTED, occurred_at
            )
        elif case.current_state not in _AUTONOMOUS_CASE_STATES:
            conversation.set_status(ConversationStatus.CLOSED, occurred_at)

    def _maybe_reactivate_lost_case(
        self,
        uow: UnitOfWork,
        conversation: Conversation,
        occurred_at: datetime,
    ) -> None:
        """Give a LOST case one more real evaluation instead of leaving the
        conversation stuck on the same static qualification.lost_message
        forever. state_machine.py already models LOST -> REACTIVATION ->
        CONTACTED, but nothing drove those transitions -- _process_message
        closed the conversation on LOST (see _synchronize_case_status /
        _AUTONOMOUS_CASE_STATES) and every later message just hit
        _paused_response.

        Only reactivates ProcessState.LOST specifically -- CANCELLED, PAID,
        and COMPLETED stay genuinely terminal (state_machine.py has no
        REACTIVATION transition defined from any of them either). This can
        only help: the very next message goes through the normal
        qualification path again, so a real correction (wrong zip, typo)
        gets genuinely re-qualified, while a customer who's still
        correctly out of scope reaches the same LOST outcome and sees the
        same lost_message either way -- no worse than before.
        """
        if conversation.case_id is None or conversation.status is not ConversationStatus.CLOSED:
            return
        case = uow.cases.get(conversation.business_id, conversation.case_id)
        if case is None or case.current_state is not ProcessState.LOST:
            return
        attempts = int(conversation.metadata.get("reactivation_attempts", 0) or 0)
        if attempts >= self.MAX_REACTIVATION_ATTEMPTS:
            return

        for target in (ProcessState.REACTIVATION, ProcessState.CONTACTED):
            expected = case.version
            existing_event_count = len(case.event_history)
            event = ProcessEvent(
                EventType.TRIGGER_RECEIVED,
                occurred_at=occurred_at,
                source="conversation_service",
                payload={
                    "reason": "Customer sent a new message after LOST",
                    "requested_target": target.value,
                },
            )
            self.intake.process_engine.receive(case, event, DecisionRequest(DecisionType.RULE, target))
            uow.cases.save(case, expected)
            uow.events.add_many(
                case.business_id, case.case_id, case.event_history[existing_event_count:]
            )

        conversation.metadata["reactivation_attempts"] = attempts + 1
        conversation.set_status(ConversationStatus.AI_ACTIVE, occurred_at)

    def _run_intake(
        self,
        uow: UnitOfWork,
        conversation: Conversation,
        message_text: str,
        external_message_id: str,
        occurred_at: datetime,
        prior_messages: tuple[ConversationMessage, ...],
        *,
        sms_consent: bool = False,
    ) -> LeadIntakeResult:
        context = self._context(uow, conversation, prior_messages)
        internal_message_id = "chat:" + hashlib.sha256(
            f"{conversation.conversation_id}\x1f{external_message_id}".encode("utf-8")
        ).hexdigest()
        return self.intake.receive_in_unit_of_work(uow, IncomingMessage(
            business_id=conversation.business_id,
            channel=self.CHANNEL,
            external_message_id=internal_message_id,
            raw_text=message_text,
            timestamp=occurred_at,
            case_id=conversation.case_id,
            conversation_context=context,
            sms_consent=sms_consent,
        ))

    def _context(
        self,
        uow: UnitOfWork,
        conversation: Conversation,
        prior_messages: tuple[ConversationMessage, ...],
    ) -> ConversationContext:
        known_facts: dict[str, Any] = {}
        current_state = self._stored_state(conversation)
        if conversation.case_id is not None:
            case = uow.cases.get(conversation.business_id, conversation.case_id)
            if case is None or case.lead.lead_id != conversation.lead_id:
                raise RuntimeError("conversation references an invalid tenant case")
            current_state = case.current_state
            for key in (
                "service_requested",
                "customer_location",
                "preferred_time",
                "urgency",
                "qualification_answers",
            ):
                value = case.lead.attributes.get(key)
                if value is not None:
                    known_facts[key] = value
        recent = tuple(
            ConversationContextMessage(message.role, self._redact_contact(message.text))
            for message in prior_messages[-self.CONTEXT_MESSAGE_LIMIT:]
            if message.role in {MessageRole.CUSTOMER, MessageRole.ASSISTANT}
        )
        unresolved = tuple(
            str(item) for item in conversation.metadata.get("unresolved_items", [])
        )
        return ConversationContext(
            recent_messages=recent,
            known_facts=known_facts,
            unresolved_items=unresolved,
            current_state=current_state.value if current_state else None,
        )

    @staticmethod
    def _redact_contact(text: str) -> str:
        return _PHONE.sub("[phone redacted]", _EMAIL.sub("[email redacted]", text))

    @staticmethod
    def _response_for_result(
        result: LeadIntakeResult,
        dna: Mapping[str, Any],
    ) -> tuple[str, str]:
        if result.response is not None:
            return result.response.message_text, result.response.reason
        if result.current_state is ProcessState.QUALIFIED:
            return ConversationService._chat_text(
                dna,
                "qualified_message",
                "Thanks — we have the information needed. A team member can help with the next step.",
            ), "qualified"
        raise RuntimeError("intake result has no customer-safe response")

    @staticmethod
    def _paused_response(
        conversation: Conversation,
        dna: Mapping[str, Any],
    ) -> tuple[str, str]:
        if conversation.status in {
            ConversationStatus.HUMAN_TAKEOVER_REQUESTED,
            ConversationStatus.HUMAN_TAKEOVER_ACTIVE,
        }:
            escalation = dna.get("human_escalation", {})
            if not isinstance(escalation, Mapping) or not isinstance(
                escalation.get("customer_message"), str
            ):
                raise RuntimeError("Business DNA has no safe human escalation response")
            return str(escalation["customer_message"]), "human_escalation"
        state = ConversationService._stored_state(conversation)
        if state is ProcessState.LOST:
            qualification = dna.get("qualification", {})
            if isinstance(qualification, Mapping) and isinstance(
                qualification.get("lost_message"), str
            ):
                return str(qualification["lost_message"]), "not_qualified"
        if state is ProcessState.QUALIFIED:
            return ConversationService._chat_text(
                dna,
                "qualified_message",
                "Thanks — we have the information needed. A team member can help with the next step.",
            ), "qualified"
        return ConversationService._chat_text(
            dna,
            "closed_message",
            "This conversation is complete. Please contact the business if you need more help.",
        ), "conversation_closed"

    @staticmethod
    def _unresolved_items(
        result: LeadIntakeResult,
        dna: Mapping[str, Any],
    ) -> tuple[str, ...]:
        items = [f"field:{field_name}" for field_name in result.qualification.missing_fields]
        prompt_to_id: dict[str, str] = {}
        for service in dna.get("services", []):
            if not isinstance(service, Mapping):
                continue
            if service.get("id") != result.qualification.service_id:
                continue
            for question in service.get("qualification_questions", []):
                if isinstance(question, Mapping):
                    prompt = question.get("prompt")
                    question_id = question.get("id")
                    if isinstance(prompt, str) and isinstance(question_id, str):
                        prompt_to_id[prompt] = question_id
        for prompt in result.qualification.unanswered_questions:
            question_id = prompt_to_id.get(prompt)
            if question_id is None:
                raise RuntimeError("qualification result references an unknown configured question")
            items.append(f"question:{question_id}")
        return tuple(items)

    @staticmethod
    def _track_questions(
        conversation: Conversation,
        result: LeadIntakeResult,
        dna: Mapping[str, Any],
        occurred_at: datetime,
    ) -> None:
        unresolved = set(ConversationService._unresolved_items(result, dna))
        tracking = {
            str(item.get("key")): dict(item)
            for item in conversation.metadata.get("questions", [])
            if isinstance(item, Mapping) and isinstance(item.get("key"), str)
        }
        for item in tracking.values():
            if item["key"] not in unresolved:
                item["answered"] = True
        for key in unresolved:
            item = tracking.setdefault(key, {"key": key, "asked_count": 0})
            item["asked_count"] = int(item.get("asked_count", 0)) + 1
            item["last_asked_at"] = occurred_at.astimezone(timezone.utc).isoformat()
            item["answered"] = False
        conversation.metadata["questions"] = [tracking[key] for key in sorted(tracking)]

    @staticmethod
    def _chat_text(dna: Mapping[str, Any], key: str, fallback: str) -> str:
        widget = dna.get("chat_widget", {})
        value = widget.get(key) if isinstance(widget, Mapping) else None
        return value.strip() if isinstance(value, str) and value.strip() else fallback

    @staticmethod
    def _active_dna(uow: UnitOfWork, business_id: str) -> Mapping[str, Any]:
        if uow.businesses.get(business_id) is None:
            raise KeyError(f"unknown business_id: {business_id}")
        version = uow.business_dna.get_active(business_id)
        if version is None:
            raise RuntimeError("business has no active Business DNA")
        return PersistentLeadIntakeService._plain_json(version.configuration)

    @staticmethod
    def _ensure_public_chat_enabled(dna: Mapping[str, Any]) -> None:
        communication = dna.get("communication", {})
        channels = communication.get("channels", []) if isinstance(communication, Mapping) else []
        widget = dna.get("chat_widget", {})
        enabled = widget.get("enabled", False) if isinstance(widget, Mapping) else False
        if not enabled or ConversationService.CHANNEL not in channels:
            raise MessageScopeError("public chat is not enabled for this business")

    @staticmethod
    def _stored_state(conversation: Conversation) -> ProcessState | None:
        value = conversation.metadata.get("current_state")
        return ProcessState(value) if isinstance(value, str) else None

    @staticmethod
    def _snapshot(
        uow: UnitOfWork,
        conversation: Conversation,
        token: str,
        *,
        duplicate: bool = False,
    ) -> PublicConversation:
        messages = uow.conversation_messages.list_for_conversation(
            conversation.business_id,
            conversation.conversation_id,
            limit=ConversationService.PUBLIC_HISTORY_LIMIT,
        )
        current_state = ConversationService._stored_state(conversation)
        status = conversation.status
        if conversation.case_id is not None:
            case = uow.cases.get(conversation.business_id, conversation.case_id)
            if case is None or case.lead.lead_id != conversation.lead_id:
                raise RuntimeError("conversation references an invalid tenant case")
            current_state = case.current_state
            if status is ConversationStatus.AI_ACTIVE:
                if current_state is ProcessState.NEEDS_HUMAN:
                    status = ConversationStatus.HUMAN_TAKEOVER_REQUESTED
                elif current_state not in _AUTONOMOUS_CASE_STATES:
                    status = ConversationStatus.CLOSED
        return PublicConversation(
            internal_conversation_id=conversation.conversation_id,
            conversation_token=token,
            status=status,
            current_state=current_state,
            requires_human=status in {
                ConversationStatus.HUMAN_TAKEOVER_REQUESTED,
                ConversationStatus.HUMAN_TAKEOVER_ACTIVE,
            },
            messages=tuple(
                PublicConversationMessage(
                    message.direction,
                    message.role,
                    message.text,
                    message.created_at,
                )
                for message in messages
            ),
            duplicate=duplicate,
        )

    @staticmethod
    def hash_token(token: str) -> str:
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise ConversationTokenError("conversation token has an invalid format")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_new_token(token: str) -> None:
        if len(token) != 43 or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise ConversationTokenError("new conversation token has an invalid format")
        try:
            decoded = base64.urlsafe_b64decode(token + "=")
        except ValueError as exc:
            raise ConversationTokenError("new conversation token has an invalid encoding") from exc
        if len(decoded) != 32:
            raise ConversationTokenError("new conversation token must contain 256 bits")

    @staticmethod
    def _validate_conversation_token(conversation: Conversation | None) -> None:
        if conversation is None:
            raise ConversationTokenError("conversation token was not found for tenant")
        now = utc_now()
        if conversation.token_revoked_at is not None or conversation.token_expires_at <= now:
            raise ConversationTokenExpiredError("conversation token is expired or revoked")
