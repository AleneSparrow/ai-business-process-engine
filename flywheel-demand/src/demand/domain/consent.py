"""Permission records for loyalty mailings. Consent is never inferred from copy."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from src.demand.domain.primitives import require_aware, require_text, utc_now


class ConsentChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"


class ConsentAction(StrEnum):
    GRANT = "grant"
    REVOKE = "revoke"


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    channel: ConsentChannel
    action: ConsentAction
    source: str
    recorded_at: datetime = field(default_factory=utc_now)
    evidence_id: str | None = None

    def __post_init__(self) -> None:
        require_text(self.source, "source")
        require_aware(self.recorded_at, "recorded_at")
        if self.evidence_id is not None:
            require_text(self.evidence_id, "evidence_id")
        if self.channel is ConsentChannel.SMS and self.action is ConsentAction.GRANT:
            if not (self.evidence_id or "").strip():
                raise ValueError("SMS grant requires written-consent evidence_id (TCPA)")
