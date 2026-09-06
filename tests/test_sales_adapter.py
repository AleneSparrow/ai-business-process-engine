"""Tests for the experimental evidence-grounding/domain-construction adapter.

Scope: docs/agent-prompts/claude-code-sales-knowledge-and-evals.md,
2026-09-06 code-review pass, item 5. Pure unit tests -- no network, no
provider, no SalesPolicyEngine involvement.
"""

from datetime import datetime, timezone

import pytest

from src.ai.sales_adapter import UngroundedEvidenceError, build_sales_turn_analysis, check_evidence_grounded
from src.ai.sales_models import SalesTurnAnalysisOutput
from src.domain.sales import (
    CommitmentLevel,
    CustomerEvidence,
    ObjectionType,
    SalesMove,
    SalesStage,
    SalesTurnAnalysis,
)


CUSTOMER_MESSAGE = "That's way more than I expected to pay"


def _output(**overrides: object) -> SalesTurnAnalysisOutput:
    value: dict[str, object] = {
        "observed_stage": "OBJECTION_HANDLING",
        "confidence": 0.9,
        "customer_intent": "pushes back on the price",
        "signals": [],
        "objections": [
            {
                "objection_type": "PRICE",
                "status": "ACTIVE",
                "evidence": CUSTOMER_MESSAGE,
                "cause": None,
            }
        ],
        "commitment_level": "CONSIDERING",
        "recommended_moves": ["DIAGNOSE_OBJECTION"],
        "requested_callback_at": None,
        "requires_human": False,
    }
    value.update(overrides)
    return SalesTurnAnalysisOutput.model_validate(value)


def test_check_evidence_grounded_accepts_verbatim_evidence() -> None:
    assert check_evidence_grounded(_output(), CUSTOMER_MESSAGE) == []


def test_check_evidence_grounded_rejects_a_fabricated_quote() -> None:
    output = _output(
        objections=[
            {
                "objection_type": "PRICE",
                "status": "ACTIVE",
                "evidence": "this exact phrase never appears in the message",
                "cause": None,
            }
        ]
    )
    violations = check_evidence_grounded(output, CUSTOMER_MESSAGE)
    assert len(violations) == 1
    assert "not a verbatim substring" in violations[0]


def test_check_evidence_grounded_rejects_a_quote_only_present_in_history() -> None:
    """The model sometimes grabs a phrase from an earlier turn instead of the
    current message -- this must be rejected exactly like a fabrication,
    since the function is only ever given the current message."""
    history_only_phrase = "we talked about this being too expensive last week"
    output = _output(
        objections=[
            {
                "objection_type": "PRICE",
                "status": "ACTIVE",
                "evidence": history_only_phrase,
                "cause": None,
            }
        ]
    )
    # The current message does not contain history_only_phrase at all.
    violations = check_evidence_grounded(output, CUSTOMER_MESSAGE)
    assert violations
    assert all("not a verbatim substring" in v for v in violations)


def test_check_evidence_grounded_checks_signals_too() -> None:
    output = _output(
        objections=[],
        observed_stage="DISCOVERY",
        recommended_moves=[],
        signals=[{"kind": "timeline", "value": "next month", "evidence": "made up quote"}],
    )
    violations = check_evidence_grounded(output, CUSTOMER_MESSAGE)
    assert len(violations) == 1
    assert "signal[kind='timeline']" in violations[0]


def test_build_sales_turn_analysis_with_grounded_evidence_succeeds() -> None:
    analysis = build_sales_turn_analysis(
        _output(), source_message_id="msg-123", customer_message=CUSTOMER_MESSAGE
    )
    assert isinstance(analysis, SalesTurnAnalysis)
    assert analysis.observed_stage is SalesStage.OBJECTION_HANDLING
    assert analysis.commitment_level is CommitmentLevel.CONSIDERING
    assert analysis.recommended_moves == (SalesMove.DIAGNOSE_OBJECTION,)
    assert len(analysis.objections) == 1
    assert analysis.objections[0].objection_type is ObjectionType.PRICE
    assert analysis.objections[0].evidence.excerpt == CUSTOMER_MESSAGE


def test_build_sales_turn_analysis_raises_on_fabricated_evidence() -> None:
    output = _output(
        objections=[
            {
                "objection_type": "PRICE",
                "status": "ACTIVE",
                "evidence": "invented quote not in the message",
                "cause": None,
            }
        ]
    )
    with pytest.raises(UngroundedEvidenceError):
        build_sales_turn_analysis(output, source_message_id="msg-123", customer_message=CUSTOMER_MESSAGE)


def test_build_sales_turn_analysis_does_not_partially_build_on_violation() -> None:
    """A grounding violation must refuse to build anything at all, not
    silently drop the bad signal/objection and return a partial object."""
    output = _output(
        objections=[
            {"objection_type": "PRICE", "status": "ACTIVE", "evidence": CUSTOMER_MESSAGE, "cause": None},
            {"objection_type": "TRUST", "status": "ACTIVE", "evidence": "fabricated", "cause": None},
        ]
    )
    with pytest.raises(UngroundedEvidenceError):
        build_sales_turn_analysis(output, source_message_id="msg-123", customer_message=CUSTOMER_MESSAGE)


def test_build_sales_turn_analysis_uses_the_given_source_message_id() -> None:
    analysis = build_sales_turn_analysis(
        _output(), source_message_id="msg-source-42", customer_message=CUSTOMER_MESSAGE
    )
    for objection in analysis.objections:
        assert objection.evidence.source_message_id == "msg-source-42"


def test_build_sales_turn_analysis_does_not_reword_evidence() -> None:
    analysis = build_sales_turn_analysis(
        _output(), source_message_id="msg-123", customer_message=CUSTOMER_MESSAGE
    )
    assert analysis.objections[0].evidence.excerpt == CUSTOMER_MESSAGE


def test_build_sales_turn_analysis_converts_callback_datetime_safely() -> None:
    output = _output(
        observed_stage="COMMITMENT",
        objections=[],
        recommended_moves=["SCHEDULE_CALLBACK"],
        requested_callback_at="2026-09-07T15:00:00+00:00",
    )
    analysis = build_sales_turn_analysis(output, source_message_id="msg-123", customer_message=CUSTOMER_MESSAGE)
    assert analysis.requested_callback_at == datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)


def test_build_sales_turn_analysis_metadata_comes_only_from_the_caller() -> None:
    """Metadata must never be populated from model output -- pass a
    server-controlled dict and confirm nothing from `output` leaks into it,
    and that omitting it entirely defaults to empty rather than borrowing
    anything from the model's own customer_intent/signals/etc."""
    server_metadata = {"prompt_version": "2026-09-06.v2", "model": "claude-sonnet-5"}
    analysis = build_sales_turn_analysis(
        _output(), source_message_id="msg-123", customer_message=CUSTOMER_MESSAGE, metadata=server_metadata
    )
    assert dict(analysis.metadata) == server_metadata

    analysis_without_metadata = build_sales_turn_analysis(
        _output(), source_message_id="msg-123", customer_message=CUSTOMER_MESSAGE
    )
    assert dict(analysis_without_metadata.metadata) == {}


def test_build_sales_turn_analysis_builds_a_real_customer_evidence() -> None:
    analysis = build_sales_turn_analysis(
        _output(), source_message_id="msg-123", customer_message=CUSTOMER_MESSAGE
    )
    evidence = analysis.objections[0].evidence
    assert isinstance(evidence, CustomerEvidence)
