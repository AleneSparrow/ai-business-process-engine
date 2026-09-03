"""Demand campaign and prospect aggregates."""

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from src.demand.domain.primitives import freeze, require_aware, require_text, utc_now

from .consent import ConsentAction, ConsentChannel, ConsentRecord
from .states import CampaignState, ProspectState


def _require_id(value: str, field_name: str) -> None:
    require_text(value, field_name)


@dataclass(frozen=True, slots=True)
class CampaignEvent:
    event_type: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=utc_now)
    payload: Mapping[str, Any] = field(default_factory=dict)
    causation_id: str | None = None

    def __post_init__(self) -> None:
        require_text(self.event_type, "event_type")
        require_text(self.event_id, "event_id")
        require_aware(self.occurred_at, "occurred_at")
        object.__setattr__(self, "payload", freeze(self.payload))


@dataclass(frozen=True, slots=True)
class ProspectEvent:
    event_type: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=utc_now)
    payload: Mapping[str, Any] = field(default_factory=dict)
    causation_id: str | None = None

    def __post_init__(self) -> None:
        require_text(self.event_type, "event_type")
        require_text(self.event_id, "event_id")
        require_aware(self.occurred_at, "occurred_at")
        object.__setattr__(self, "payload", freeze(self.payload))


@dataclass(frozen=True, slots=True)
class ContentBrief:
    brief_id: str
    stage: str
    format: str
    job: str
    summary: str
    allowed_claim_ids: tuple[str, ...] = ()
    cta: str = "none"
    channel: str = "web"

    def __post_init__(self) -> None:
        for name in ("brief_id", "stage", "format", "job", "summary", "cta", "channel"):
            require_text(getattr(self, name), name)
        object.__setattr__(self, "allowed_claim_ids", tuple(self.allowed_claim_ids))


@dataclass(frozen=True, slots=True)
class SequenceStep:
    index: int
    offset_hours: int
    purpose: str
    channel: str
    summary: str
    allowed_claim_ids: tuple[str, ...] = ()
    cta: str = "none"
    requires_consent: ConsentChannel = ConsentChannel.EMAIL

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("sequence step index must be >= 1")
        if self.offset_hours < 0:
            raise ValueError("offset_hours must be >= 0")
        require_text(self.purpose, "purpose")
        require_text(self.channel, "channel")
        require_text(self.summary, "summary")
        require_text(self.cta, "cta")
        object.__setattr__(self, "allowed_claim_ids", tuple(self.allowed_claim_ids))


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    channel: str
    subject: str
    body: str
    cta: str
    claim_ids: tuple[str, ...] = ()
    sequence_index: int | None = None
    brief_id: str | None = None

    def __post_init__(self) -> None:
        require_text(self.channel, "channel")
        require_text(self.body, "body")
        object.__setattr__(self, "claim_ids", tuple(self.claim_ids))


@dataclass(slots=True, init=False)
class Campaign:
    campaign_id: str
    business_id: str
    _current_state: CampaignState
    marketing_dna: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int
    _event_history: list[CampaignEvent]
    _processed_event_ids: set[str]
    _pending_transition: CampaignState | None

    def __init__(
        self,
        campaign_id: str,
        business_id: str,
        marketing_dna: Mapping[str, Any],
        current_state: CampaignState = CampaignState.MARKET_ANALYSIS,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        _require_id(campaign_id, "campaign_id")
        _require_id(business_id, "business_id")
        now = utc_now()
        self.campaign_id = campaign_id
        self.business_id = business_id
        self._current_state = current_state
        self.marketing_dna = MappingProxyType({key: freeze(value) for key, value in dict(marketing_dna).items()})
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self.version = version
        self._event_history = []
        self._processed_event_ids = set()
        self._pending_transition = None
        require_aware(self.created_at, "created_at")
        require_aware(self.updated_at, "updated_at")

    @property
    def current_state(self) -> CampaignState:
        return self._current_state

    @property
    def pending_transition(self) -> CampaignState | None:
        return self._pending_transition

    @property
    def event_history(self) -> tuple[CampaignEvent, ...]:
        return tuple(self._event_history)

    def has_processed(self, event_id: str) -> bool:
        return event_id in self._processed_event_ids

    def record(self, event: CampaignEvent) -> None:
        self._event_history.append(event)

    def mark_processed(self, event_id: str) -> None:
        self._processed_event_ids.add(event_id)

    def _apply_transition(self, target: CampaignState) -> None:
        self._current_state = target
        self._pending_transition = None
        self.updated_at = utc_now()
        self.version += 1

    def escalate(self, pending: CampaignState) -> None:
        self._pending_transition = pending
        self._current_state = CampaignState.NEEDS_HUMAN
        self.updated_at = utc_now()
        self.version += 1


@dataclass(slots=True, init=False)
class Prospect:
    prospect_id: str
    business_id: str
    campaign_id: str
    _current_state: ProspectState
    name: str | None
    email: str | None
    phone: str | None
    score: int
    next_sequence_index: int
    subscribed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    attributes: Mapping[str, Any]
    _consent: list[ConsentRecord]
    _event_history: list[ProspectEvent]
    _processed_event_ids: set[str]
    _pending_transition: ProspectState | None
    _handoff_id: str | None

    def __init__(
        self,
        prospect_id: str,
        business_id: str,
        campaign_id: str,
        current_state: ProspectState = ProspectState.UNKNOWN,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        score: int = 0,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        _require_id(prospect_id, "prospect_id")
        _require_id(business_id, "business_id")
        _require_id(campaign_id, "campaign_id")
        now = utc_now()
        self.prospect_id = prospect_id
        self.business_id = business_id
        self.campaign_id = campaign_id
        self._current_state = current_state
        self.name = name
        self.email = email
        self.phone = phone
        self.score = score
        self.next_sequence_index = 1
        self.subscribed_at = None
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self.version = version
        self.attributes = MappingProxyType({key: freeze(value) for key, value in dict(attributes or {}).items()})
        self._consent = []
        self._event_history = []
        self._processed_event_ids = set()
        self._pending_transition = None
        self._handoff_id = None
        require_aware(self.created_at, "created_at")
        require_aware(self.updated_at, "updated_at")
        if self.name is not None:
            require_text(self.name, "name")
        if self.email is not None:
            require_text(self.email, "email")
        if self.phone is not None:
            require_text(self.phone, "phone")

    @property
    def current_state(self) -> ProspectState:
        return self._current_state

    @property
    def pending_transition(self) -> ProspectState | None:
        return self._pending_transition

    @property
    def event_history(self) -> tuple[ProspectEvent, ...]:
        return tuple(self._event_history)

    @property
    def consent_history(self) -> tuple[ConsentRecord, ...]:
        return tuple(self._consent)

    @property
    def handoff_id(self) -> str | None:
        return self._handoff_id

    def has_processed(self, event_id: str) -> bool:
        return event_id in self._processed_event_ids

    def record(self, event: ProspectEvent) -> None:
        self._event_history.append(event)

    def mark_processed(self, event_id: str) -> None:
        self._processed_event_ids.add(event_id)

    def add_consent(self, record: ConsentRecord) -> None:
        self._consent.append(record)

    def has_active_consent(self, channel: ConsentChannel) -> bool:
        latest: ConsentRecord | None = None
        for record in self._consent:
            if record.channel is channel:
                latest = record
        return latest is not None and latest.action is ConsentAction.GRANT

    def _apply_transition(self, target: ProspectState) -> None:
        self._current_state = target
        self._pending_transition = None
        self.updated_at = utc_now()
        self.version += 1

    def escalate(self, pending: ProspectState) -> None:
        self._pending_transition = pending
        self._current_state = ProspectState.NEEDS_HUMAN
        self.updated_at = utc_now()
        self.version += 1

    def mark_handed_off(self, handoff_id: str) -> None:
        require_text(handoff_id, "handoff_id")
        self._handoff_id = handoff_id
