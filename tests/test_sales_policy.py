from datetime import datetime, timezone

import pytest

from src.domain.sales import (
    CommitmentLevel,
    CustomerEvidence,
    CustomerSalesProfile,
    ObjectionStatus,
    ObjectionType,
    SalesMove,
    SalesObjection,
    SalesStage,
    SalesTurnAnalysis,
)
from src.engine.sales_policy import (
    InvalidSalesStageTransition,
    SalesPolicyEngine,
    SalesStageMachine,
)


def _profile(**overrides: object) -> CustomerSalesProfile:
    values = {
        "business_id": "biz-1",
        "case_id": "case-1",
        "stage": SalesStage.DISCOVERY,
    }
    values.update(overrides)
    return CustomerSalesProfile(**values)  # type: ignore[arg-type]


def _analysis(**overrides: object) -> SalesTurnAnalysis:
    values = {"observed_stage": SalesStage.DISCOVERY, "confidence": 0.9}
    values.update(overrides)
    return SalesTurnAnalysis(**values)  # type: ignore[arg-type]


def _objection(*, status: ObjectionStatus, cause: str | None = None) -> SalesObjection:
    return SalesObjection(
        objection_type=ObjectionType.PRICE,
        status=status,
        evidence=CustomerEvidence("message-1", "That is more than I expected"),
        cause=cause,
    )


def test_sales_stage_machine_is_separate_and_closed() -> None:
    machine = SalesStageMachine()
    machine.validate(SalesStage.GREETING, SalesStage.DISCOVERY)
    with pytest.raises(InvalidSalesStageTransition, match="GREETING to WON"):
        machine.validate(SalesStage.GREETING, SalesStage.WON)
    with pytest.raises(ValueError, match="every SalesStage"):
        SalesStageMachine({SalesStage.GREETING: frozenset({SalesStage.DISCOVERY})})


def test_human_review_has_highest_policy_precedence() -> None:
    decision = SalesPolicyEngine().decide(
        _profile(current_problem="missed leads", desired_outcome="book more calls"),
        _analysis(requires_human=True, commitment_level=CommitmentLevel.READY_FOR_NEXT_STEP),
        approved_knowledge_available=True,
        booking_available=True,
    )
    assert decision.move is SalesMove.HANDOFF_TO_HUMAN
    assert decision.requires_human


def test_new_objection_is_diagnosed_before_any_commitment() -> None:
    decision = SalesPolicyEngine().decide(
        _profile(current_problem="missed leads", desired_outcome="book more calls"),
        _analysis(
            objections=(_objection(status=ObjectionStatus.ACTIVE),),
            commitment_level=CommitmentLevel.READY_FOR_NEXT_STEP,
        ),
        approved_knowledge_available=True,
        booking_available=True,
    )
    assert decision.move is SalesMove.DIAGNOSE_OBJECTION
    assert decision.target_stage is SalesStage.OBJECTION_HANDLING


def test_diagnosed_objection_needs_approved_knowledge() -> None:
    analysis = _analysis(objections=(_objection(status=ObjectionStatus.DIAGNOSED, cause="value"),))
    without_knowledge = SalesPolicyEngine().decide(_profile(), analysis)
    with_knowledge = SalesPolicyEngine().decide(
        _profile(), analysis, approved_knowledge_available=True
    )
    assert without_knowledge.move is SalesMove.HANDOFF_TO_HUMAN
    assert with_knowledge.move is SalesMove.ANSWER_OBJECTION
    assert with_knowledge.knowledge_required


def test_addressed_objection_must_be_checked_not_assumed_resolved() -> None:
    decision = SalesPolicyEngine().decide(
        _profile(),
        _analysis(objections=(_objection(status=ObjectionStatus.ADDRESSED, cause="value"),)),
        approved_knowledge_available=True,
    )
    assert decision.move is SalesMove.CHECK_OBJECTION_RESOLUTION


def test_missing_discovery_context_asks_a_question() -> None:
    decision = SalesPolicyEngine().decide(_profile(current_problem="missed leads"), _analysis())
    assert decision.move is SalesMove.ASK_DISCOVERY_QUESTION
    assert decision.target_stage is SalesStage.DISCOVERY


def test_explicit_callback_request_precedes_discovery() -> None:
    callback_at = datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc)
    decision = SalesPolicyEngine().decide(
        _profile(),
        _analysis(requested_callback_at=callback_at),
    )
    assert decision.move is SalesMove.SCHEDULE_CALLBACK
    assert decision.target_stage is SalesStage.FOLLOW_UP


def test_ready_customer_gets_slots_only_when_booking_is_available() -> None:
    profile = _profile(
        stage=SalesStage.COMMITMENT,
        current_problem="missed leads",
        desired_outcome="book more calls",
    )
    analysis = _analysis(commitment_level=CommitmentLevel.READY_FOR_NEXT_STEP)
    unavailable = SalesPolicyEngine().decide(profile, analysis, booking_available=False)
    available = SalesPolicyEngine().decide(profile, analysis, booking_available=True)
    assert unavailable.move is SalesMove.ASK_FOR_COMMITMENT
    assert available.move is SalesMove.OFFER_BOOKING_SLOTS

