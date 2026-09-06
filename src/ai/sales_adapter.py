"""Experimental adapter: validated AI output -> real domain.sales objects.

Scope note (docs/agent-prompts/claude-code-sales-knowledge-and-evals.md,
2026-09-06 code-review pass): this module is NOT wired into any production
orchestration path, the API, or SalesPolicyEngine. It exists so the
evidence-grounding check that used to live only inside
scripts/sales_turn_analysis_eval.py has one canonical, testable
implementation, and so that "converting SalesTurnAnalysisOutput into a real
SalesTurnAnalysis" is an actual, reviewable function rather than an assumed
1:1 mapping -- it is not 1:1: the domain object additionally needs a
caller-supplied `source_message_id` (CustomerEvidence requires one per
excerpt, and this schema has nowhere to carry it -- it is always about "the
current message", identified by the caller, not the model) and
server-controlled audit metadata that must never be populated from anything
the model said.
"""

from collections.abc import Mapping
from typing import Any

from src.ai.errors import AIInvalidOutputError
from src.ai.sales_models import SalesTurnAnalysisOutput
from src.domain.sales import (
    CustomerEvidence,
    SalesObjection,
    SalesSignal,
    SalesTurnAnalysis,
)


class UngroundedEvidenceError(AIInvalidOutputError):
    """A signal or objection's `evidence` did not occur verbatim in the
    current customer message -- e.g. it was fabricated, paraphrased, or
    copied from CONVERSATION_CONTEXT instead of the message being analyzed.
    Reuses AIInvalidOutputError's category/shape since this is the same kind
    of failure (the model returned output that fails validation) as every
    other invalid-output case in this codebase; `metadata` is optional here
    because this check runs after a provider call has already succeeded and
    is not itself a provider call."""

    category = "ungrounded_evidence"


def check_evidence_grounded(output: SalesTurnAnalysisOutput, customer_message: str) -> list[str]:
    """Return a list of human-readable violations (empty = fully grounded).

    Checks ONLY against `customer_message` -- the current turn's raw text --
    never against conversation history, so evidence copied from an earlier
    turn (a plausible model mistake) is rejected exactly like a fabricated
    quote would be. Pure function: no I/O, no mutation of `output`.
    """
    violations: list[str] = []
    for signal in output.signals:
        if signal.evidence not in customer_message:
            violations.append(
                f"signal[kind={signal.kind!r}].evidence {signal.evidence!r} is not a verbatim "
                "substring of the current customer message"
            )
    for objection in output.objections:
        if objection.evidence not in customer_message:
            violations.append(
                f"objection[type={objection.objection_type.value}].evidence {objection.evidence!r} "
                "is not a verbatim substring of the current customer message"
            )
    return violations


def build_sales_turn_analysis(
    output: SalesTurnAnalysisOutput,
    *,
    source_message_id: str,
    customer_message: str,
    metadata: Mapping[str, Any] | None = None,
) -> SalesTurnAnalysis:
    """Validate `output` against `customer_message`, then build the real
    domain.sales.SalesTurnAnalysis.

    - Every signal/objection evidence string must be an exact, unmodified
      substring of `customer_message` (never conversation history) -- see
      check_evidence_grounded. Raises UngroundedEvidenceError and builds
      nothing if any evidence fails this check; it never silently drops the
      offending signal/objection and continues with a partial result.
    - `source_message_id` is a server-controlled argument (the id of the
      message being analyzed) and is attached, unchanged, to every
      CustomerEvidence built here -- it is never read from `output`, which
      has no such field.
    - `requested_callback_at` is already a timezone-aware `datetime`
      (SalesTurnAnalysisOutput's field type is pydantic's AwareDatetime,
      which parses and rejects naive/malformed input before this function
      ever runs) -- this function passes it straight through; the domain
      field has the identical type and constraint (see
      domain.sales.SalesTurnAnalysis.__post_init__'s `_require_aware` call),
      so no further conversion is needed or performed here.
    - `metadata`, if given, is attached to the domain object as-is. It must
      come only from server-controlled context (e.g. prompt/model
      identifiers, timing) -- nothing from `output` is ever merged into it,
      by construction: this function simply never reads `output` for that
      purpose.
    - Evidence text itself is copied through unmodified -- this function
      never corrects, trims beyond what the domain layer itself requires, or
      rephrases it.
    """
    violations = check_evidence_grounded(output, customer_message)
    if violations:
        raise UngroundedEvidenceError(
            "SalesTurnAnalysisOutput evidence failed grounding check: " + "; ".join(violations)
        )

    signals = tuple(
        SalesSignal(
            kind=signal.kind,
            value=signal.value,
            evidence=CustomerEvidence(source_message_id=source_message_id, excerpt=signal.evidence),
        )
        for signal in output.signals
    )
    objections = tuple(
        SalesObjection(
            objection_type=objection.objection_type,
            status=objection.status,
            evidence=CustomerEvidence(source_message_id=source_message_id, excerpt=objection.evidence),
            cause=objection.cause,
        )
        for objection in output.objections
    )
    return SalesTurnAnalysis(
        observed_stage=output.observed_stage,
        confidence=output.confidence,
        customer_intent=output.customer_intent,
        signals=signals,
        objections=objections,
        commitment_level=output.commitment_level,
        recommended_moves=tuple(output.recommended_moves),
        requested_callback_at=output.requested_callback_at,
        requires_human=output.requires_human,
        metadata=dict(metadata) if metadata is not None else {},
    )
