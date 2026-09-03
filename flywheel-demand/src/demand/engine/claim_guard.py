"""FTC-style claim guard: only approved, substantiated claims may be published."""

from __future__ import annotations

import re
from typing import Mapping

from src.demand.domain.claims import Claim, ClaimStatus
from src.demand.domain.marketing_dna import claims_from_dna

_SUPERLATIVE = re.compile(
    r"(?i)\b(best|#1|number\s+one|guaranteed?|100\s*%|risk[\s-]?free)\b",
)


class UnsubstantiatedClaimError(ValueError):
    """Outbound copy used a claim the Marketing DNA does not allow."""


def approved_claims(marketing_dna: Mapping[str, object]) -> tuple[Claim, ...]:
    return tuple(claim for claim in claims_from_dna(marketing_dna) if claim.publishable)


def _mask_approved(text: str, claims: tuple[Claim, ...]) -> str:
    masked = text
    for claim in claims:
        if claim.text and claim.text in masked:
            masked = masked.replace(claim.text, " " * len(claim.text))
    return masked


def assert_publishable(text: str, marketing_dna: Mapping[str, object]) -> None:
    if not (text or "").strip():
        raise UnsubstantiatedClaimError("outbound text must not be empty")
    allowed = approved_claims(marketing_dna)
    remainder = _mask_approved(text, allowed)
    match = _SUPERLATIVE.search(remainder)
    if match:
        raise UnsubstantiatedClaimError(
            f"unsubstantiated superlative {match.group(0)!r} is not an approved claim"
        )


def assert_claims_allowed(claim_ids: tuple[str, ...], marketing_dna: Mapping[str, object]) -> None:
    allowed = {claim.claim_id for claim in approved_claims(marketing_dna)}
    for claim_id in claim_ids:
        if claim_id not in allowed:
            raise UnsubstantiatedClaimError(f"claim {claim_id!r} is not approved for publication")


def is_blocked_claim(claim: Claim) -> bool:
    return claim.status is ClaimStatus.BLOCKED or not claim.publishable
