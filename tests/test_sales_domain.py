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


def test_sales_turn_analysis_requires_closed_enum_values() -> None:
    with pytest.raises(TypeError, match="SalesStage"):
        SalesTurnAnalysis(observed_stage="DISCOVERY", confidence=0.9)  # type: ignore[arg-type]


def test_sales_turn_analysis_rejects_duplicate_recommendations() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        SalesTurnAnalysis(
            observed_stage=SalesStage.DISCOVERY,
            confidence=0.9,
            recommended_moves=(SalesMove.ASK_DISCOVERY_QUESTION, SalesMove.ASK_DISCOVERY_QUESTION),
        )


def test_customer_evidence_is_required_and_bounded() -> None:
    with pytest.raises(ValueError, match="excerpt"):
        CustomerEvidence("message-1", "")
    with pytest.raises(ValueError, match="500"):
        CustomerEvidence("message-1", "x" * 501)


def test_callback_time_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SalesTurnAnalysis(
            observed_stage=SalesStage.COMMITMENT,
            confidence=1.0,
            requested_callback_at=datetime(2026, 9, 5, 12, 0),
        )


def test_sales_profile_rejects_duplicate_decision_criteria() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        CustomerSalesProfile(
            business_id="biz-1",
            case_id="case-1",
            decision_criteria=("price", "price"),
        )


def test_objection_is_grounded_in_customer_evidence() -> None:
    objection = SalesObjection(
        objection_type=ObjectionType.PRICE,
        status=ObjectionStatus.ACTIVE,
        evidence=CustomerEvidence("message-1", "That is more than I expected"),
    )
    analysis = SalesTurnAnalysis(
        observed_stage=SalesStage.OBJECTION_HANDLING,
        confidence=0.96,
        objections=(objection,),
        commitment_level=CommitmentLevel.CONSIDERING,
    )
    assert analysis.objections[0].evidence.source_message_id == "message-1"


def test_sales_metadata_is_frozen() -> None:
    analysis = SalesTurnAnalysis(
        observed_stage=SalesStage.DISCOVERY,
        confidence=0.8,
        metadata={"provider": {"name": "anthropic"}},
    )
    with pytest.raises(TypeError):
        analysis.metadata["provider"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        analysis.metadata["provider"]["name"] = "other"  # type: ignore[index]


def test_aware_callback_time_is_accepted() -> None:
    callback_at = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    analysis = SalesTurnAnalysis(
        observed_stage=SalesStage.COMMITMENT,
        confidence=1.0,
        requested_callback_at=callback_at,
    )
    assert analysis.requested_callback_at == callback_at

