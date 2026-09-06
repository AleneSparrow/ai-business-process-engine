"""Deterministic authorization boundary for generated sales responses."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from src.domain.sales import SalesMove


_UNAUTHORIZED_EXECUTION = re.compile(
    r"\b(?:your (?:booking|appointment) is confirmed|you(?:'ve| have) been booked|"
    r"payment (?:was|has been) processed|refund (?:was|has been) issued|"
    r"discount (?:was|has been) applied)\b",
    re.IGNORECASE,
)
_SENSITIVE_CLAIM = re.compile(
    r"(?:[$€£]\s?\d[\d,.]*|\b\d{1,3}\s*%|\b(?:discount|guarantee|guaranteed|"
    r"free (?:trial|consultation|service|visit|estimate|upgrade)|for free|no cost|"
    r"limited time|only \d+ (?:spots?|slots?) left)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SalesResponseCandidate:
    message_text: str
    move: SalesMove
    knowledge_ids: tuple[str, ...] = ()
    business_fact_ids: tuple[str, ...] = ()
    customer_evidence_ids: tuple[str, ...] = ()
    used_safe_fallback: bool = False


@dataclass(frozen=True, slots=True)
class SalesResponseValidationContext:
    approved_move: SalesMove
    approved_knowledge: frozenset[str]
    approved_business_facts: Mapping[str, str]
    customer_evidence: Mapping[str, str]
    safe_fallback: str
    knowledge_required: bool = False
    booking_available: bool = False
    callback_at: datetime | None = None
    contact_allowed: bool = True
    human_takeover_active: bool = False

    def __post_init__(self) -> None:
        if not self.safe_fallback.strip():
            raise ValueError("safe_fallback must not be empty")
        if self.callback_at is not None and (
            self.callback_at.tzinfo is None or self.callback_at.utcoffset() is None
        ):
            raise ValueError("callback_at must include a timezone")


@dataclass(frozen=True, slots=True)
class SalesResponseValidationResult:
    valid: bool
    message_text: str
    violations: tuple[str, ...]
    used_fallback: bool


class SalesPolicyValidator:
    """Rejects unauthorized IDs, claims, moves and tool-like commitments."""

    def validate(
        self,
        candidate: SalesResponseCandidate,
        context: SalesResponseValidationContext,
    ) -> SalesResponseValidationResult:
        violations: list[str] = []
        text = candidate.message_text.strip()
        if not text:
            violations.append("empty_message")
        if candidate.move is not context.approved_move:
            violations.append("move_mismatch")
        self._check_unique(candidate.knowledge_ids, "duplicate_knowledge_id", violations)
        self._check_unique(candidate.business_fact_ids, "duplicate_business_fact_id", violations)
        self._check_unique(candidate.customer_evidence_ids, "duplicate_evidence_id", violations)

        if not set(candidate.knowledge_ids).issubset(context.approved_knowledge):
            violations.append("unapproved_knowledge_id")
        if not set(candidate.business_fact_ids).issubset(context.approved_business_facts):
            violations.append("unknown_business_fact_id")
        if not set(candidate.customer_evidence_ids).issubset(context.customer_evidence):
            violations.append("unknown_customer_evidence_id")
        if context.knowledge_required and not candidate.knowledge_ids and not candidate.used_safe_fallback:
            violations.append("required_knowledge_missing")
        if candidate.used_safe_fallback:
            if text != context.safe_fallback.strip():
                violations.append("safe_fallback_text_mismatch")
            if candidate.knowledge_ids or candidate.business_fact_ids:
                violations.append("safe_fallback_has_grounding_ids")

        if not context.contact_allowed:
            if context.approved_move is not SalesMove.END_CONTACT or text != context.safe_fallback.strip():
                violations.append("contact_not_allowed")
            if candidate.knowledge_ids or candidate.business_fact_ids:
                violations.append("contact_suppression_has_sales_content")
        if context.human_takeover_active:
            if (
                context.approved_move is not SalesMove.HANDOFF_TO_HUMAN
                or text != context.safe_fallback.strip()
            ):
                violations.append("human_takeover_active")
        if candidate.move is SalesMove.OFFER_BOOKING_SLOTS and not context.booking_available:
            violations.append("booking_not_available")
        if candidate.move is SalesMove.SCHEDULE_CALLBACK and context.callback_at is None:
            violations.append("callback_time_missing")
        if _UNAUTHORIZED_EXECUTION.search(text):
            violations.append("unauthorized_commercial_execution")

        referenced_facts = "\n".join(
            context.approved_business_facts[fact_id]
            for fact_id in candidate.business_fact_ids
            if fact_id in context.approved_business_facts
        )
        for claim in _SENSITIVE_CLAIM.findall(text):
            if claim.casefold() not in referenced_facts.casefold():
                violations.append("ungrounded_sensitive_claim")
                break

        unique_violations = tuple(dict.fromkeys(violations))
        return SalesResponseValidationResult(
            valid=not unique_violations,
            message_text=text if not unique_violations else context.safe_fallback,
            violations=unique_violations,
            used_fallback=bool(unique_violations),
        )

    @staticmethod
    def _check_unique(values: tuple[str, ...], code: str, violations: list[str]) -> None:
        if len(set(values)) != len(values):
            violations.append(code)
