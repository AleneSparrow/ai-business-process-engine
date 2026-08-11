"""Dependency-free domain models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from .states import ProcessState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


class DecisionType(StrEnum):
    RULE = "RULE"
    AI = "AI"
    HUMAN = "HUMAN"


@dataclass(frozen=True, slots=True)
class Lead:
    lead_id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.lead_id, "lead_id")
        if self.name is not None:
            _require_text(self.name, "name")
        object.__setattr__(self, "attributes", _freeze(self.attributes))


@dataclass(frozen=True, slots=True)
class ProcessEvent:
    event_type: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=utc_now)
    payload: Mapping[str, Any] = field(default_factory=dict)
    source: str = "system"
    causation_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.event_type, "event_type")
        _require_text(self.event_id, "event_id")
        _require_text(self.source, "source")
        _require_aware(self.occurred_at, "occurred_at")
        object.__setattr__(self, "payload", _freeze(self.payload))


@dataclass(frozen=True, slots=True)
class Decision:
    decision_type: DecisionType
    approved: bool
    reason: str
    target_state: ProcessState | None = None
    confidence: float | None = None
    requires_human: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.reason, "reason")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class Action:
    action_type: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    high_risk: bool = False
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.action_type, "action_type")
        object.__setattr__(self, "parameters", _freeze(self.parameters))


@dataclass(frozen=True, slots=True)
class ActionResult:
    action: Action
    succeeded: bool
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    completed_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_aware(self.completed_at, "completed_at")
        object.__setattr__(self, "data", _freeze(self.data))


@dataclass(slots=True, init=False)
class ProcessCase:
    case_id: str
    business_id: str
    lead: Lead
    _current_state: ProcessState
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]
    version: int
    _event_history: list[ProcessEvent] = field(default_factory=list, init=False, repr=False)
    _processed_event_ids: set[str] = field(default_factory=set, init=False, repr=False)
    _pending_transition: ProcessState | None = field(default=None, init=False, repr=False)

    def __init__(
        self,
        case_id: str,
        business_id: str,
        lead: Lead,
        current_state: ProcessState = ProcessState.NEW_LEAD,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
        version: int = 0,
        pending_transition: ProcessState | None = None,
        event_history: tuple[ProcessEvent, ...] = (),
    ) -> None:
        self.case_id = case_id
        self.business_id = business_id
        self.lead = lead
        self._current_state = current_state
        self.created_at = created_at or utc_now()
        self.updated_at = updated_at or self.created_at
        self.metadata = dict(metadata or {})
        self.version = version
        self._event_history = list(event_history)
        self._processed_event_ids = set()
        self._pending_transition = pending_transition
        _require_text(self.case_id, "case_id")
        _require_text(self.business_id, "business_id")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.version < 0:
            raise ValueError("version must not be negative")
        if self._pending_transition is not None and self._current_state is not ProcessState.NEEDS_HUMAN:
            raise ValueError("pending_transition is only valid for NEEDS_HUMAN cases")

    @property
    def event_history(self) -> tuple[ProcessEvent, ...]:
        return tuple(self._event_history)

    @property
    def current_state(self) -> ProcessState:
        return self._current_state

    @property
    def pending_transition(self) -> ProcessState | None:
        return self._pending_transition

    def record(self, event: ProcessEvent) -> None:
        self._event_history.append(event)
        self.updated_at = max(self.updated_at, utc_now())

    def has_processed(self, event_id: str) -> bool:
        return event_id in self._processed_event_ids

    def mark_processed(self, event_id: str) -> None:
        self._processed_event_ids.add(event_id)

    def set_pending_transition(self, target: ProcessState) -> None:
        self._pending_transition = target

    def clear_pending_transition(self) -> None:
        self._pending_transition = None

    def _apply_transition(self, target: ProcessState) -> None:
        """Apply a transition already authorized by the process engine."""
        self._current_state = target

    def update_lead(self, lead: Lead) -> None:
        if lead.lead_id != self.lead.lead_id:
            raise ValueError("updated lead must preserve lead_id")
        self.lead = lead

    def mark_persisted(self, version: int) -> None:
        if version <= self.version:
            raise ValueError("persisted version must advance")
        self.version = version
