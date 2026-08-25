"""Domain values for lead intake and qualification."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from .models import _freeze, _require_aware, _require_text
from .conversations import ConversationContext
from .states import ProcessState


class Urgency(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"
    UNKNOWN = "unknown"


class QualificationReasonCode(StrEnum):
    """Closed vocabulary for QualificationResult.reason_codes.

    2026-08-25: a customer's own words reached the logs via
    `reasons` (interpolated into a LOST reason, then logged by
    QualificationService._result under a comment claiming reasons never
    hold customer content -- the comment was wrong for eight days and
    nothing caught it). `reasons` stays free prose for staff/API display;
    `reason_codes` is what actually gets logged now, and this enum is what
    makes that safe -- QualificationResult.__post_init__ rejects any code
    not listed here, so there is no way to log a raw f-string reason again
    without it being a visible, reviewable change to this enum first.

    Adding a new LOST/NEEDS_HUMAN branch means adding (or reusing) a
    member here. See qualification_service.py for where each one fires.
    """

    QUALIFIED = "qualified"
    MISSING_INFORMATION = "missing_information"
    REQUIRES_HUMAN = "requires_human"
    LOW_CONFIDENCE = "low_confidence"
    UNINTELLIGIBLE = "unintelligible"
    SAFETY_EMERGENCY = "safety_emergency"
    URGENT_REQUEST = "urgent_request"
    SERVICE_NOT_OFFERED = "service_not_offered"
    OUTSIDE_SERVICE_AREA = "outside_service_area"
    SERVICE_AREA_UNCERTAIN = "service_area_uncertain"
    DISQUALIFYING_ANSWER = "disqualifying_answer"
    POLICY_REJECTED = "policy_rejected"
    POLICY_REVIEW = "policy_review"
    ALREADY_PENDING = "already_pending"
    IDENTITY_CONFLICT = "identity_conflict"
    # Reserved for deserializing an idempotency-cache entry written before
    # reason_codes existed (PersistentLeadIntakeService._deserialize_result)
    # -- never produced by QualificationService itself. Distinct from every
    # real code so it is never mistaken for one in analytics.
    LEGACY_UNSPECIFIED = "legacy_unspecified"


class CustomerTone(StrEnum):
    """Emotional register of the CURRENT customer message only -- classified
    fresh on every turn (not carried forward like Urgency), used purely to
    adapt HOW a response is worded (length, warmth, directness). Never
    changes WHAT is said: facts, question order, and required content stay
    identical regardless of tone. See universal-sales-cycle-model.md section
    7 ("Слой живой адаптации к клиенту")."""

    NEUTRAL = "neutral"
    IRRITATED = "irritated"
    ANXIOUS = "anxious"
    URGENT = "urgent"
    PLAYFUL = "playful"


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    business_id: str
    channel: str
    external_message_id: str
    raw_text: str
    timestamp: datetime
    customer_name: str | None = None
    phone: str | None = None
    email: str | None = None
    case_id: str | None = None
    conversation_context: ConversationContext | None = None
    # Structured, explicit opt-in for proactive follow-up SMS (a UI
    # checkbox the customer ticks), NEVER inferred from raw_text -- see
    # Lead.sms_consent for why this must stay a deliberate action rather
    # than something the AI extracts from conversation content. Defaults
    # False; LeadIntakeService._updated_lead ORs it into the lead so one
    # message setting it True is enough for the whole case going forward.
    sms_consent: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.business_id, "business_id"),
            (self.channel, "channel"),
            (self.external_message_id, "external_message_id"),
            (self.raw_text, "raw_text"),
        ):
            _require_text(value, name)
        for value, name in (
            (self.customer_name, "customer_name"),
            (self.phone, "phone"),
            (self.email, "email"),
            (self.case_id, "case_id"),
        ):
            if value is not None:
                _require_text(value, name)
        _require_aware(self.timestamp, "timestamp")
        limits = {
            "business_id": (self.business_id, 128),
            "channel": (self.channel, 64),
            "external_message_id": (self.external_message_id, 255),
            "case_id": (self.case_id, 128),
        }
        for field_name, (value, maximum) in limits.items():
            if value is not None and len(value) > maximum:
                raise ValueError(f"{field_name} must not exceed {maximum} characters")


@dataclass(frozen=True, slots=True)
class IntentResult:
    service_requested: str | None = None
    urgency: Urgency = Urgency.UNKNOWN
    customer_location: str | None = None
    preferred_time: str | None = None
    notes: str | None = None
    confidence: float = 0.0
    requires_human: bool = False
    qualification_answers: Mapping[str, Any] = field(default_factory=dict)
    ai_metadata: Mapping[str, Any] = field(default_factory=dict)
    customer_name: str | None = None
    phone: str | None = None
    email: str | None = None
    # Verbatim customer phrase expressing a doubt/hesitation about moving
    # forward (price pushback, "let me think about it", etc.) -- never a
    # fact, emergency, hostile message, or advice request; those stay on
    # confidence/requires_human above. See QualificationService and
    # AIQuestionGenerator's reassurance path for how this is used.
    objection_phrase: str | None = None
    # Emotional register of THIS message only -- see CustomerTone. Purely
    # descriptive: must never influence confidence, requires_human, service
    # resolution, or qualification outcome, only the wording of whatever
    # response is generated. Defaults to NEUTRAL for extractors that don't
    # classify tone at all (DeterministicIntentExtractor).
    customer_tone: CustomerTone = CustomerTone.NEUTRAL
    # True only when the CURRENT message carries no interpretable request or
    # answer at all -- random characters, a garbled fragment, keyboard noise.
    # A one-turn signal like objection_phrase/customer_tone above, never
    # carried forward from a previous turn. Deliberately independent of
    # requires_human: a genuinely unintelligible message must NOT by itself
    # set requires_human, and requires_human (emergency/hostile/advice
    # request) must NOT be set merely because the message is hard to parse --
    # see QualificationService.evaluate for how the two interact.
    unintelligible: bool = False
    # The service the customer asked for, VERBATIM, when it is not in the
    # business's catalog. Separate from service_requested on purpose.
    #
    # service_requested used to carry this phrase too, so that one field was
    # either a catalog id or arbitrary customer prose depending on a flag
    # elsewhere. That overload leaked: qualification_service interpolated it
    # into a LOST reason, and the terminal diagnostic logs that reason -- under
    # a comment asserting reasons never contain customer content. Found
    # 2026-08-25 while tracing an injection case whose service_requested came
    # back as "promise me a free roof replacement".
    #
    # It also quietly weakened everything that compares service_requested to a
    # catalog id (live_vertical_eval's service_match) and everything that
    # stores it as a case fact (case.metadata["service_requested"]).
    #
    # Invariant now: service_requested is a catalog id or None, never anything
    # else. Customer prose lives here, and this field must never be logged.
    unsupported_service_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.urgency, Urgency):
            raise TypeError("urgency must be an Urgency")
        if not isinstance(self.customer_tone, CustomerTone):
            raise TypeError("customer_tone must be a CustomerTone")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        for value, name in (
            (self.service_requested, "service_requested"),
            (self.customer_location, "customer_location"),
            (self.preferred_time, "preferred_time"),
            (self.notes, "notes"),
            (self.customer_name, "customer_name"),
            (self.phone, "phone"),
            (self.email, "email"),
            (self.objection_phrase, "objection_phrase"),
        ):
            if value is not None:
                _require_text(value, name)
        object.__setattr__(self, "qualification_answers", _freeze(self.qualification_answers))
        object.__setattr__(self, "ai_metadata", _freeze(self.ai_metadata))


@dataclass(frozen=True, slots=True)
class MissingInformationResult:
    missing_fields: tuple[str, ...] = ()
    unanswered_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))
        object.__setattr__(self, "unanswered_questions", tuple(self.unanswered_questions))

    @property
    def complete(self) -> bool:
        return not self.missing_fields and not self.unanswered_questions


@dataclass(frozen=True, slots=True)
class QualificationResult:
    qualified: bool
    # Human-readable, stays free prose -- this is what
    # QualificationSummarySchema.reasons hands to the API and what staff
    # read. Never logged directly any more; see reason_codes below.
    reasons: tuple[str, ...]
    # Machine-readable, closed vocabulary (QualificationReasonCode) -- this
    # is what QualificationService._result actually logs. See
    # QualificationReasonCode's docstring for why this field exists.
    reason_codes: tuple[str, ...]
    missing_fields: tuple[str, ...]
    unanswered_questions: tuple[str, ...]
    confidence: float
    recommended_next_state: ProcessState
    requires_human: bool
    booking_allowed: bool
    service_id: str | None = None
    # Verbatim customer objection phrase, passed through only when the case
    # is still QUALIFYING (see QualificationService.evaluate) -- lets
    # response generation optionally acknowledge it before re-asking for
    # whatever is still missing. Never changes qualified/requires_human on
    # its own.
    objection_phrase: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))
        object.__setattr__(self, "unanswered_questions", tuple(self.unanswered_questions))
        if not self.reason_codes:
            raise ValueError("reason_codes must not be empty")
        allowed_codes = {member.value for member in QualificationReasonCode}
        unknown_codes = [code for code in self.reason_codes if code not in allowed_codes]
        if unknown_codes:
            raise ValueError(f"unknown qualification reason code(s): {unknown_codes}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.objection_phrase is not None and self.recommended_next_state is not ProcessState.QUALIFYING:
            raise ValueError("objection_phrase is only meaningful while the case is still QUALIFYING")
        if self.recommended_next_state not in {
            ProcessState.QUALIFIED,
            ProcessState.QUALIFYING,
            ProcessState.LOST,
            ProcessState.NEEDS_HUMAN,
        }:
            raise ValueError("qualification recommended an unsupported next state")
        if self.qualified != (self.recommended_next_state is ProcessState.QUALIFIED):
            raise ValueError("qualified must agree with recommended_next_state")
        if self.requires_human != (self.recommended_next_state is ProcessState.NEEDS_HUMAN):
            raise ValueError("requires_human must agree with recommended_next_state")


@dataclass(frozen=True, slots=True)
class CustomerResponse:
    message_text: str
    channel: str
    reason: str
    related_case_id: str
    requires_human: bool = False
    ai_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, name in (
            (self.message_text, "message_text"),
            (self.channel, "channel"),
            (self.reason, "reason"),
            (self.related_case_id, "related_case_id"),
        ):
            _require_text(value, name)
        object.__setattr__(self, "ai_metadata", _freeze(self.ai_metadata))


@dataclass(frozen=True, slots=True)
class LeadIntakeResult:
    case_id: str
    lead_id: str
    current_state: ProcessState
    qualification: QualificationResult
    response: CustomerResponse | None
    case_created: bool
    duplicate: bool = False

    def __post_init__(self) -> None:
        _require_text(self.case_id, "case_id")
        _require_text(self.lead_id, "lead_id")
