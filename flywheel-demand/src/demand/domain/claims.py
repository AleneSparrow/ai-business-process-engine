"""Approved marketing claims. AI cannot invent these; the owner or Business DNA can."""

from dataclasses import dataclass
from enum import StrEnum

from src.demand.domain.primitives import require_text


class SubstantiationKind(StrEnum):
    BUSINESS_DNA = "business_dna"
    OWNER_SUPPLIED = "owner_supplied"
    NONE = "none"


class ClaimStatus(StrEnum):
    APPROVED = "approved"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    text: str
    substantiation: SubstantiationKind
    status: ClaimStatus
    evidence: str = ""

    def __post_init__(self) -> None:
        require_text(self.claim_id, "claim_id")
        require_text(self.text, "text")
        if self.substantiation is SubstantiationKind.NONE:
            object.__setattr__(self, "status", ClaimStatus.BLOCKED)
        elif self.substantiation is SubstantiationKind.OWNER_SUPPLIED and not (self.evidence or "").strip():
            object.__setattr__(self, "status", ClaimStatus.BLOCKED)

    @property
    def publishable(self) -> bool:
        return self.status is ClaimStatus.APPROVED and self.substantiation is not SubstantiationKind.NONE
