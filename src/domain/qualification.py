"""Domain values for lead intake and qualification."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from .models import _freeze, _require_aware, _require_text
from .states import ProcessState


class Urgency(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"
    UNKNOWN = "unknown"


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

    def __post_init__(self) -> None:
        if not isinstance(self.urgency, Urgency):
            raise TypeError("urgency must be an Urgency")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        for value, name in (
            (self.service_requested, "service_requested"),
            (self.customer_location, "customer_location"),
            (self.preferred_time, "preferred_time"),
            (self.notes, "notes"),
        ):
            if value is not None:
                _require_text(value, name)
        object.__setattr__(self, "qualification_answers", _freeze(self.qualification_answers))


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
    reasons: tuple[str, ...]
    missing_fields: tuple[str, ...]
    unanswered_questions: tuple[str, ...]
    confidence: float
    recommended_next_state: ProcessState
    requires_human: bool
    booking_allowed: bool
    service_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))
        object.__setattr__(self, "unanswered_questions", tuple(self.unanswered_questions))
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
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

    def __post_init__(self) -> None:
        for value, name in (
            (self.message_text, "message_text"),
            (self.channel, "channel"),
            (self.reason, "reason"),
            (self.related_case_id, "related_case_id"),
        ):
            _require_text(value, name)


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
