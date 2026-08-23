"""Non-sensitive, stable reason codes for staff escalation observability."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from .qualification import IntentResult, QualificationResult, Urgency


class EscalationReason(StrEnum):
    SAFETY_EMERGENCY = "safety_emergency"
    URGENT_REQUEST = "urgent_request"
    LOW_CONFIDENCE = "low_confidence"
    SERVICE_UNCLEAR = "service_unclear"
    UNINTELLIGIBLE = "unintelligible"
    AI_REVIEW = "ai_review"
    SERVICE_AREA_UNCERTAIN = "service_area_uncertain"
    POLICY_REVIEW = "policy_review"
    IDENTITY_CONFLICT = "identity_conflict"
    ALREADY_PENDING = "already_pending"


def escalation_reason(
    intent: IntentResult,
    qualification: QualificationResult,
    business_dna: Mapping[str, Any],
) -> str | None:
    """Classify an escalation from validated facts, never customer text."""
    if not qualification.requires_human:
        return None
    reasons = " ".join(qualification.reasons).casefold()
    if "could not be interpreted" in reasons:
        return EscalationReason.UNINTELLIGIBLE.value
    if "already awaiting" in reasons:
        return EscalationReason.ALREADY_PENDING.value
    if "contact identity" in reasons:
        return EscalationReason.IDENTITY_CONFLICT.value
    if intent.urgency is Urgency.EMERGENCY:
        return EscalationReason.SAFETY_EMERGENCY.value
    if intent.urgency is Urgency.HIGH:
        return EscalationReason.URGENT_REQUEST.value
    if "service area" in reasons:
        return EscalationReason.SERVICE_AREA_UNCERTAIN.value
    if "configured qualification policy" in reasons:
        return EscalationReason.POLICY_REVIEW.value
    permissions = business_dna.get("ai_permissions", {})
    threshold = (
        float(permissions.get("minimum_confidence", 0.8))
        if isinstance(permissions, Mapping)
        else 0.8
    )
    if intent.confidence < threshold:
        return EscalationReason.LOW_CONFIDENCE.value
    if intent.service_requested is None:
        return EscalationReason.SERVICE_UNCLEAR.value
    return EscalationReason.AI_REVIEW.value
