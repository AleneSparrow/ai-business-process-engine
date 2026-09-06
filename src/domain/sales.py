"""Provider-neutral domain contracts for the governed sales conversation layer.

SalesStage describes conversational progress. It is intentionally separate
from ProcessState, which remains authoritative for business commitments.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from .models import _freeze, _require_aware, _require_text


class SalesStage(StrEnum):
    GREETING = "GREETING"
    DISCOVERY = "DISCOVERY"
    NEEDS_CONFIRMED = "NEEDS_CONFIRMED"
    PRESENTATION = "PRESENTATION"
    OBJECTION_HANDLING = "OBJECTION_HANDLING"
    COMMITMENT = "COMMITMENT"
    BOOKING = "BOOKING"
    NURTURE = "NURTURE"
    FOLLOW_UP = "FOLLOW_UP"
    WON = "WON"
    LOST = "LOST"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class SalesMove(StrEnum):
    GREET_AND_SET_CONTEXT = "GREET_AND_SET_CONTEXT"
    ASK_DISCOVERY_QUESTION = "ASK_DISCOVERY_QUESTION"
    REFLECT_CUSTOMER_NEED = "REFLECT_CUSTOMER_NEED"
    CONFIRM_CUSTOMER_NEED = "CONFIRM_CUSTOMER_NEED"
    PRESENT_RELEVANT_VALUE = "PRESENT_RELEVANT_VALUE"
    PROVIDE_APPROVED_PROOF = "PROVIDE_APPROVED_PROOF"
    DIAGNOSE_OBJECTION = "DIAGNOSE_OBJECTION"
    ANSWER_OBJECTION = "ANSWER_OBJECTION"
    CHECK_OBJECTION_RESOLUTION = "CHECK_OBJECTION_RESOLUTION"
    ASK_FOR_COMMITMENT = "ASK_FOR_COMMITMENT"
    OFFER_BOOKING_SLOTS = "OFFER_BOOKING_SLOTS"
    SCHEDULE_CALLBACK = "SCHEDULE_CALLBACK"
    SEND_CONTEXTUAL_FOLLOW_UP = "SEND_CONTEXTUAL_FOLLOW_UP"
    NURTURE_WITHOUT_PRESSURE = "NURTURE_WITHOUT_PRESSURE"
    HANDOFF_TO_HUMAN = "HANDOFF_TO_HUMAN"
    END_CONTACT = "END_CONTACT"


class ObjectionType(StrEnum):
    PRICE = "PRICE"
    TRUST = "TRUST"
    TIMING = "TIMING"
    FIT = "FIT"
    AUTHORITY = "AUTHORITY"
    COMPETITOR = "COMPETITOR"
    NEED_TO_THINK = "NEED_TO_THINK"
    OTHER = "OTHER"


class ObjectionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DIAGNOSED = "DIAGNOSED"
    ADDRESSED = "ADDRESSED"
    RESOLVED = "RESOLVED"
    DEFERRED = "DEFERRED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class CommitmentLevel(StrEnum):
    UNKNOWN = "UNKNOWN"
    CURIOUS = "CURIOUS"
    INTERESTED = "INTERESTED"
    CONSIDERING = "CONSIDERING"
    READY_FOR_NEXT_STEP = "READY_FOR_NEXT_STEP"
    DECLINED = "DECLINED"


class SalesKnowledgeStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SalesPlaybookStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class CustomerEvidence:
    """An exact customer excerpt supporting one structured sales signal."""

    source_message_id: str
    excerpt: str

    def __post_init__(self) -> None:
        _require_text(self.source_message_id, "source_message_id")
        _require_text(self.excerpt, "excerpt")
        if len(self.source_message_id) > 255:
            raise ValueError("source_message_id must not exceed 255 characters")
        if len(self.excerpt) > 500:
            raise ValueError("evidence excerpt must not exceed 500 characters")


@dataclass(frozen=True, slots=True)
class SalesSignal:
    """A classified signal that cannot exist without customer evidence."""

    kind: str
    value: str
    evidence: CustomerEvidence

    def __post_init__(self) -> None:
        _require_text(self.kind, "kind")
        _require_text(self.value, "value")
        if len(self.kind) > 100:
            raise ValueError("signal kind must not exceed 100 characters")
        if len(self.value) > 500:
            raise ValueError("signal value must not exceed 500 characters")


@dataclass(frozen=True, slots=True)
class SalesObjection:
    objection_type: ObjectionType
    status: ObjectionStatus
    evidence: CustomerEvidence
    cause: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.objection_type, ObjectionType):
            raise TypeError("objection_type must be an ObjectionType")
        if not isinstance(self.status, ObjectionStatus):
            raise TypeError("status must be an ObjectionStatus")
        if self.cause is not None:
            _require_text(self.cause, "cause")
            if len(self.cause) > 500:
                raise ValueError("objection cause must not exceed 500 characters")


@dataclass(frozen=True, slots=True)
class SalesTurnAnalysis:
    """Validated language analysis. Recommendations never authorize a move."""

    observed_stage: SalesStage
    confidence: float
    customer_intent: str | None = None
    signals: tuple[SalesSignal, ...] = ()
    objections: tuple[SalesObjection, ...] = ()
    commitment_level: CommitmentLevel = CommitmentLevel.UNKNOWN
    recommended_moves: tuple[SalesMove, ...] = ()
    requested_callback_at: datetime | None = None
    requires_human: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.observed_stage, SalesStage):
            raise TypeError("observed_stage must be a SalesStage")
        if not isinstance(self.commitment_level, CommitmentLevel):
            raise TypeError("commitment_level must be a CommitmentLevel")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.customer_intent is not None:
            _require_text(self.customer_intent, "customer_intent")
        signals = tuple(self.signals)
        objections = tuple(self.objections)
        recommendations = tuple(self.recommended_moves)
        if any(not isinstance(item, SalesSignal) for item in signals):
            raise TypeError("signals must contain SalesSignal values")
        if any(not isinstance(item, SalesObjection) for item in objections):
            raise TypeError("objections must contain SalesObjection values")
        if any(not isinstance(item, SalesMove) for item in recommendations):
            raise TypeError("recommended_moves must contain SalesMove values")
        if len(set(recommendations)) != len(recommendations):
            raise ValueError("recommended_moves must not contain duplicates")
        if self.requested_callback_at is not None:
            _require_aware(self.requested_callback_at, "requested_callback_at")
        object.__setattr__(self, "signals", signals)
        object.__setattr__(self, "objections", objections)
        object.__setattr__(self, "recommended_moves", recommendations)
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class CustomerSalesProfile:
    """Persistable sales memory; no field here is a business authorization."""

    business_id: str
    case_id: str
    stage: SalesStage = SalesStage.GREETING
    customer_goal: str | None = None
    current_problem: str | None = None
    desired_outcome: str | None = None
    decision_criteria: tuple[str, ...] = ()
    active_objection: SalesObjection | None = None
    commitment_level: CommitmentLevel = CommitmentLevel.UNKNOWN
    preferred_channel: str | None = None
    preferred_contact_at: datetime | None = None
    last_move: SalesMove | None = None
    version: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.business_id, "business_id")
        _require_text(self.case_id, "case_id")
        if not isinstance(self.stage, SalesStage):
            raise TypeError("stage must be a SalesStage")
        if not isinstance(self.commitment_level, CommitmentLevel):
            raise TypeError("commitment_level must be a CommitmentLevel")
        for value, name in (
            (self.customer_goal, "customer_goal"),
            (self.current_problem, "current_problem"),
            (self.desired_outcome, "desired_outcome"),
            (self.preferred_channel, "preferred_channel"),
        ):
            if value is not None:
                _require_text(value, name)
        criteria = tuple(self.decision_criteria)
        if any(not isinstance(item, str) or not item.strip() for item in criteria):
            raise ValueError("decision_criteria must contain non-empty strings")
        if len(set(criteria)) != len(criteria):
            raise ValueError("decision_criteria must not contain duplicates")
        if self.active_objection is not None and not isinstance(self.active_objection, SalesObjection):
            raise TypeError("active_objection must be a SalesObjection")
        if self.preferred_contact_at is not None:
            _require_aware(self.preferred_contact_at, "preferred_contact_at")
        if self.last_move is not None and not isinstance(self.last_move, SalesMove):
            raise TypeError("last_move must be a SalesMove")
        if self.version < 0:
            raise ValueError("version must not be negative")
        object.__setattr__(self, "decision_criteria", criteria)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class SalesMoveDecision:
    move: SalesMove
    reason_code: str
    target_stage: SalesStage
    knowledge_required: bool = False
    requires_human: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.move, SalesMove):
            raise TypeError("move must be a SalesMove")
        if not isinstance(self.target_stage, SalesStage):
            raise TypeError("target_stage must be a SalesStage")
        _require_text(self.reason_code, "reason_code")


@dataclass(frozen=True, slots=True)
class SalesKnowledgeCard:
    knowledge_id: str
    business_id: str
    version: int
    status: SalesKnowledgeStatus
    source: Mapping[str, Any]
    principle: str
    applicable_when: tuple[str, ...]
    prohibited_when: tuple[str, ...] = ()
    required_sequence: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    approved_examples: tuple[str, ...] = ()
    created_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.knowledge_id, "knowledge_id")
        _require_text(self.business_id, "business_id")
        _require_text(self.principle, "principle")
        if self.version < 1:
            raise ValueError("knowledge card version must be positive")
        if not isinstance(self.status, SalesKnowledgeStatus):
            raise TypeError("status must be a SalesKnowledgeStatus")
        source = dict(self.source)
        for required in ("title", "location"):
            value = source.get(required)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"knowledge source must contain {required}")
        for field_name in (
            "applicable_when", "prohibited_when", "required_sequence",
            "forbidden_actions", "approved_examples",
        ):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain non-empty strings")
            object.__setattr__(self, field_name, values)
        if self.created_at is not None:
            _require_aware(self.created_at, "created_at")
        if self.reviewed_at is not None:
            _require_aware(self.reviewed_at, "reviewed_at")
        if self.reviewed_by is not None:
            _require_text(self.reviewed_by, "reviewed_by")
        if (self.reviewed_at is None) != (self.reviewed_by is None):
            raise ValueError("reviewed_at and reviewed_by must be set together")
        object.__setattr__(self, "source", _freeze(source))


@dataclass(frozen=True, slots=True)
class SalesPlaybookVersion:
    business_id: str
    version: int
    status: SalesPlaybookStatus
    configuration: Mapping[str, Any]
    created_at: datetime
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_text(self.business_id, "business_id")
        if self.version < 1:
            raise ValueError("playbook version must be positive")
        if not isinstance(self.status, SalesPlaybookStatus):
            raise TypeError("status must be a SalesPlaybookStatus")
        _require_aware(self.created_at, "created_at")
        if self.published_at is not None:
            _require_aware(self.published_at, "published_at")
            if self.published_at < self.created_at:
                raise ValueError("published_at must not precede created_at")
        if self.status is SalesPlaybookStatus.PUBLISHED and self.published_at is None:
            raise ValueError("published playbook requires published_at")
        object.__setattr__(self, "configuration", _freeze(self.configuration))


@dataclass(frozen=True, slots=True)
class SalesTurn:
    turn_id: str
    business_id: str
    case_id: str
    conversation_id: str | None
    source_message_id: str
    playbook_version: int | None
    stage_before: SalesStage
    stage_after: SalesStage
    move: SalesMove
    reason_code: str
    knowledge_ids: tuple[str, ...]
    business_fact_ids: tuple[str, ...]
    customer_evidence: tuple[CustomerEvidence, ...]
    analysis: Mapping[str, Any]
    validation: Mapping[str, Any]
    created_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.turn_id, "turn_id"), (self.business_id, "business_id"),
            (self.case_id, "case_id"), (self.source_message_id, "source_message_id"),
            (self.reason_code, "reason_code"),
        ):
            _require_text(value, name)
        if self.conversation_id is not None:
            _require_text(self.conversation_id, "conversation_id")
        if self.playbook_version is not None and self.playbook_version < 1:
            raise ValueError("playbook_version must be positive")
        if not isinstance(self.stage_before, SalesStage) or not isinstance(self.stage_after, SalesStage):
            raise TypeError("sales turn stages must be SalesStage values")
        if not isinstance(self.move, SalesMove):
            raise TypeError("move must be a SalesMove")
        for field_name in ("knowledge_ids", "business_fact_ids"):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain non-empty strings")
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
            object.__setattr__(self, field_name, values)
        evidence = tuple(self.customer_evidence)
        if any(not isinstance(item, CustomerEvidence) for item in evidence):
            raise TypeError("customer_evidence must contain CustomerEvidence values")
        _require_aware(self.created_at, "created_at")
        object.__setattr__(self, "customer_evidence", evidence)
        object.__setattr__(self, "analysis", _freeze(self.analysis))
        object.__setattr__(self, "validation", _freeze(self.validation))


@dataclass(frozen=True, slots=True)
class SalesObjectionRecord:
    objection_id: str
    business_id: str
    case_id: str
    objection: SalesObjection
    created_at: datetime
    updated_at: datetime
    version: int = 0

    def __post_init__(self) -> None:
        for value, name in (
            (self.objection_id, "objection_id"),
            (self.business_id, "business_id"),
            (self.case_id, "case_id"),
        ):
            _require_text(value, name)
        if not isinstance(self.objection, SalesObjection):
            raise TypeError("objection must be a SalesObjection")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.version < 0:
            raise ValueError("version must be non-negative")
