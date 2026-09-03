"""Handoff payload from Demand into the Business Process Engine."""

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from src.domain.models import _freeze, _require_aware, _require_text, utc_now
from src.domain.qualification import IncomingMessage
from src.domain.states import ProcessState

HANDOFF_SOURCE = "flywheel_demand"
HANDOFF_ENTRY_STATE = ProcessState.NEW_LEAD
EXTERNAL_ID_PREFIX = "demand"


@dataclass(frozen=True, slots=True)
class InquiryHandoff:
    """A person reached out themselves. Product 1 owns the rest of the cycle.

    Demand stops here. Qualification, booking, quoting, and sale are not
    Demand's job. The process engine must see this as ordinary inbound
    intake — an ``IncomingMessage`` — so Product 1's boundary stays intact.
    """

    business_id: str
    prospect_id: str
    campaign_id: str
    channel: str
    inquiry_text: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    handoff_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=utc_now)
    customer_name: str | None = None
    email: str | None = None
    phone: str | None = None
    sms_consent: bool = False
    attribution: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, name in (
            (self.business_id, "business_id"),
            (self.prospect_id, "prospect_id"),
            (self.campaign_id, "campaign_id"),
            (self.channel, "channel"),
            (self.inquiry_text, "inquiry_text"),
            (self.event_id, "event_id"),
            (self.handoff_id, "handoff_id"),
        ):
            _require_text(value, name)
        _require_aware(self.occurred_at, "occurred_at")
        object.__setattr__(self, "attribution", MappingProxyType({
            key: _freeze(value) for key, value in dict(self.attribution).items()
        }))

    @property
    def source(self) -> str:
        return HANDOFF_SOURCE

    @property
    def entry_state(self) -> ProcessState:
        return HANDOFF_ENTRY_STATE

    @property
    def external_message_id(self) -> str:
        return f"{EXTERNAL_ID_PREFIX}:{self.prospect_id}:{self.event_id}"

    def to_incoming_message(self) -> IncomingMessage:
        return IncomingMessage(
            business_id=self.business_id,
            channel=self.channel,
            external_message_id=self.external_message_id,
            raw_text=self.inquiry_text,
            timestamp=self.occurred_at,
            customer_name=self.customer_name,
            phone=self.phone,
            email=self.email,
            sms_consent=self.sms_consent,
        )
