"""Tests for the experimental SalesTurnAnalysis prompt and structured output.

Scope: docs/agent-prompts/claude-code-sales-knowledge-and-evals.md Part B,
plus the 2026-09-06 code-review fixes (versioning, cross-field invariants,
strict callback typing). Uses FakeAIProvider only -- no network call, no
SalesPolicyEngine involvement.
"""

import hashlib
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.ai import sales_prompts
from src.ai.fake_provider import FakeAIProvider
from src.ai.models import AIRequest
from src.ai.sales_models import SalesObjectionOutput, SalesTurnAnalysisOutput
from src.ai.sales_prompts import SALES_PROMPT_VERSION, sales_turn_analysis_prompt
from src.domain.sales import CommitmentLevel, ObjectionStatus, ObjectionType, SalesMove, SalesStage


def _prompt():
    return sales_turn_analysis_prompt(
        profile_context={"stage": "DISCOVERY", "current_problem": None},
        conversation_context={"messages": []},
        customer_message="that's way more than I expected to pay",
    )


def _request(output_model=SalesTurnAnalysisOutput):
    prompt = _prompt()
    return AIRequest(
        prompt.identifier,
        prompt.version,
        "sales_turn_analysis",
        prompt.system,
        prompt.user,
        output_model,
        user_prompt_cache_prefix=prompt.user_cache_prefix,
    )


def _valid_output(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "observed_stage": "OBJECTION_HANDLING",
        "confidence": 0.9,
        "customer_intent": "pushes back on the price",
        "signals": [],
        "objections": [
            {
                "objection_type": "PRICE",
                "status": "ACTIVE",
                "evidence": "that's way more than I expected to pay",
                "cause": None,
            }
        ],
        "commitment_level": "CONSIDERING",
        "recommended_moves": ["DIAGNOSE_OBJECTION"],
        "requested_callback_at": None,
        "requires_human": False,
    }
    value.update(overrides)
    return value


def test_prompt_is_versioned_and_cache_prefix_is_a_true_prefix() -> None:
    prompt = _prompt()
    assert prompt.version == SALES_PROMPT_VERSION
    assert prompt.identifier == "sales_turn_analysis"
    assert prompt.user.startswith(prompt.user_cache_prefix)
    assert prompt.user_cache_prefix != ""


def test_prompt_never_puts_customer_message_in_the_cached_prefix() -> None:
    prompt = _prompt()
    assert "that's way more than I expected to pay" not in prompt.user_cache_prefix
    assert "that's way more than I expected to pay" in prompt.user


def test_prompt_lists_only_closed_enum_values() -> None:
    # CLOSED_ENUMS lives in the per-message user block (see
    # sales_turn_analysis_prompt), not the cached system prompt.
    prompt = _prompt()
    for move in SalesMove:
        assert move.value in prompt.user
    for stage in SalesStage:
        assert stage.value in prompt.user
    # HUMAN_REVIEW is a policy decision, not a model-classifiable objection
    # status -- see SalesObjectionOutput's rationale.
    compact = prompt.user.replace(" ", "")
    assert '"ObjectionStatus":[' in compact
    assert '"HUMAN_REVIEW"' not in compact.split('"ObjectionStatus":')[1].split("]")[0]


def test_valid_structured_output_round_trips_through_fake_provider() -> None:
    provider = FakeAIProvider([_valid_output()])
    result = provider.generate(_request())
    assert result.output.observed_stage is SalesStage.OBJECTION_HANDLING
    assert result.output.objections[0].objection_type is ObjectionType.PRICE
    assert result.output.objections[0].status is ObjectionStatus.ACTIVE
    assert result.output.commitment_level is CommitmentLevel.CONSIDERING
    assert result.output.recommended_moves == [SalesMove.DIAGNOSE_OBJECTION]


def test_unknown_enum_value_is_rejected_not_coerced() -> None:
    bad = _valid_output(observed_stage="INVENTED_STAGE")
    provider = FakeAIProvider([bad])
    from src.ai.errors import AIInvalidOutputError

    with pytest.raises(AIInvalidOutputError):
        provider.generate(_request())


def test_duplicate_recommended_moves_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(recommended_moves=["DIAGNOSE_OBJECTION", "DIAGNOSE_OBJECTION"])
        )


def test_objection_status_human_review_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesObjectionOutput.model_validate(
            {
                "objection_type": "PRICE",
                "status": "HUMAN_REVIEW",
                "evidence": "that's way more than I expected to pay",
                "cause": None,
            }
        )


def test_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesTurnAnalysisOutput.model_validate(_valid_output(unexpected_field="nope"))


def test_evidence_must_be_present_in_the_actual_customer_message() -> None:
    """Mirrors the anti-hallucination check pattern in AIIntentExtractor
    (src/ai/adapters.py): this experimental module does not itself wire a
    caller, but the schema's contract (evidence copied verbatim) is only
    meaningful if callers verify it -- this test documents and checks that
    verification is possible with a plain substring check. The canonical
    implementation now lives in src.ai.sales_adapter -- see
    tests/test_sales_adapter.py for that module's own tests."""
    output = SalesTurnAnalysisOutput.model_validate(_valid_output())
    customer_message = "that's way more than I expected to pay"
    for objection in output.objections:
        assert objection.evidence in customer_message


# ---------------------------------------------------------------------------
# 2026-09-06 code review: prompt versioning
# ---------------------------------------------------------------------------


def test_prompt_version_was_bumped_for_the_2026_09_06_content_changes() -> None:
    # Hardcoded literal, not just "equals the imported constant" -- this is
    # the test the task asked for: it fails if SALES_PROMPT_VERSION is ever
    # reverted to (or left at) an old value.
    assert SALES_PROMPT_VERSION == "2026-09-06.v3"


def test_ai_request_and_report_summary_carry_the_current_prompt_version() -> None:
    prompt = _prompt()
    request = _request()
    assert prompt.version == SALES_PROMPT_VERSION
    assert request.prompt_version == SALES_PROMPT_VERSION


def test_prompt_content_hash_is_pinned_to_its_version() -> None:
    """Guard against a silent prompt-text edit that doesn't bump
    SALES_PROMPT_VERSION. This hashes only the fully static parts of the
    prompt (the system text and the CLOSED_ENUMS block) -- both are
    independent of any call's inputs, so the hash is stable across calls and
    changes if and only if someone edits the prompt's actual wording or the
    domain enums it lists. If this test fails after an intentional prompt
    change: bump SALES_PROMPT_VERSION in src/ai/sales_models.py, add a
    changelog line there, then update the expected hash below to match."""
    prompt = _prompt()
    static_content = prompt.system + sales_prompts._ALLOWED_VALUES_BLOCK
    digest = hashlib.sha256(static_content.encode("utf-8")).hexdigest()
    expected_digest_by_version = {
        "2026-09-06.v3": "bbed2e958cbd516a0d88b945f20fbce9f4abe1825bfbfb4c6fce1b8672f5183d",
    }
    assert SALES_PROMPT_VERSION in expected_digest_by_version, (
        f"no pinned hash recorded for prompt version {SALES_PROMPT_VERSION} -- "
        "add one to expected_digest_by_version in this test"
    )
    assert digest == expected_digest_by_version[SALES_PROMPT_VERSION], (
        f"prompt content changed (hash={digest}) without a version bump, or the pinned hash is "
        f"stale for {SALES_PROMPT_VERSION} -- if this edit was intentional, bump "
        "SALES_PROMPT_VERSION and update this test's expected hash together"
    )


def test_old_2026_09_04_report_is_not_reinterpreted_as_the_new_version() -> None:
    """The historical live-eval report from 2026-09-04 was generated against
    prompt v1 and must stay attributed to it -- this repo must never edit
    that file to claim it reflects v2."""
    import json
    from pathlib import Path

    report_path = Path(__file__).resolve().parents[1] / "reports" / "sales-turn-analysis-eval-2026-09-04.json"
    if not report_path.exists():
        pytest.skip("historical 2026-09-04 report not present in this checkout")
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["summary"]["prompt_version"] == "2026-09-04.v1"
    assert data["summary"]["prompt_version"] != SALES_PROMPT_VERSION


# ---------------------------------------------------------------------------
# 2026-09-06 code review: strict requested_callback_at typing
# ---------------------------------------------------------------------------


def test_timezone_aware_iso_datetime_callback_is_accepted() -> None:
    output = SalesTurnAnalysisOutput.model_validate(
        _valid_output(
            observed_stage="COMMITMENT",
            objections=[],
            recommended_moves=["SCHEDULE_CALLBACK"],
            requested_callback_at="2026-09-07T15:00:00+00:00",
        )
    )
    assert output.requested_callback_at == datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)


def test_naive_datetime_callback_is_rejected() -> None:
    with pytest.raises(ValidationError, match="(?i)aware|timezone|offset"):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(
                observed_stage="COMMITMENT",
                objections=[],
                recommended_moves=["SCHEDULE_CALLBACK"],
                requested_callback_at="2026-09-07T15:00:00",
            )
        )


def test_relative_time_phrase_callback_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(
                observed_stage="COMMITMENT",
                objections=[],
                recommended_moves=["SCHEDULE_CALLBACK"],
                requested_callback_at="tomorrow at 3",
            )
        )


def test_arbitrary_string_callback_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(
                observed_stage="COMMITMENT",
                objections=[],
                recommended_moves=["SCHEDULE_CALLBACK"],
                requested_callback_at="whenever works",
            )
        )


def test_null_callback_is_accepted() -> None:
    output = SalesTurnAnalysisOutput.model_validate(_valid_output())
    assert output.requested_callback_at is None


# ---------------------------------------------------------------------------
# 2026-09-06 code review: cross-field invariants
# ---------------------------------------------------------------------------


def _objection(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "objection_type": "PRICE",
        "status": "ACTIVE",
        "evidence": "that's way more than I expected to pay",
        "cause": None,
    }
    value.update(overrides)
    return value


def test_objection_handling_stage_requires_at_least_one_objection() -> None:
    with pytest.raises(ValidationError, match="OBJECTION_HANDLING requires at least one objection"):
        SalesTurnAnalysisOutput.model_validate(_valid_output(observed_stage="OBJECTION_HANDLING", objections=[]))


def test_objection_handling_stage_with_an_objection_is_accepted() -> None:
    SalesTurnAnalysisOutput.model_validate(_valid_output())  # baseline already has one ACTIVE objection


def test_unresolved_objection_requires_objection_handling_stage() -> None:
    with pytest.raises(ValidationError, match="requires observed_stage=OBJECTION_HANDLING"):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(observed_stage="PRESENTATION", recommended_moves=["DIAGNOSE_OBJECTION"])
        )


def test_resolved_objection_does_not_require_objection_handling_stage() -> None:
    SalesTurnAnalysisOutput.model_validate(
        _valid_output(
            observed_stage="COMMITMENT",
            objections=[_objection(status="RESOLVED", cause="value_confirmed")],
            recommended_moves=["ASK_FOR_COMMITMENT"],
        )
    )


def test_active_objection_with_a_cause_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cause must be null"):
        SalesObjectionOutput.model_validate(_objection(status="ACTIVE", cause="affordability"))


def test_deferred_objection_with_a_cause_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cause must be null"):
        SalesObjectionOutput.model_validate(_objection(status="DEFERRED", cause="affordability"))


def test_diagnosed_objection_without_a_cause_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cause is required"):
        SalesObjectionOutput.model_validate(_objection(status="DIAGNOSED", cause=None))


def test_diagnosed_objection_with_a_blank_cause_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cause is required"):
        SalesObjectionOutput.model_validate(_objection(status="DIAGNOSED", cause="   "))


def test_diagnosed_objection_with_a_cause_is_accepted() -> None:
    SalesObjectionOutput.model_validate(_objection(status="DIAGNOSED", cause="affordability"))


def test_answer_objection_forbidden_while_any_objection_cause_is_null() -> None:
    with pytest.raises(ValidationError, match="ANSWER_OBJECTION requires at least one objection"):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(recommended_moves=["DIAGNOSE_OBJECTION", "ANSWER_OBJECTION"])
        )


def test_answer_objection_forbidden_with_zero_objections() -> None:
    """2026-09-06.v3 regression test: live eval found the model recommending
    ANSWER_OBJECTION with objections=[] entirely (nothing to answer) --
    v2's guard only checked existing objections' cause, missing this case."""
    with pytest.raises(ValidationError, match="ANSWER_OBJECTION requires at least one objection"):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(
                observed_stage="PRESENTATION",
                objections=[],
                recommended_moves=["ANSWER_OBJECTION"],
            )
        )


def test_answer_objection_allowed_once_cause_is_set() -> None:
    SalesTurnAnalysisOutput.model_validate(
        _valid_output(
            objections=[_objection(status="DIAGNOSED", cause="affordability")],
            recommended_moves=["ANSWER_OBJECTION"],
        )
    )


def test_requires_human_true_requires_exactly_handoff_to_human() -> None:
    with pytest.raises(ValidationError, match="requires_human=true requires recommended_moves"):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(
                observed_stage="DISCOVERY",
                objections=[],
                requires_human=True,
                recommended_moves=["HANDOFF_TO_HUMAN", "ASK_DISCOVERY_QUESTION"],
            )
        )


def test_requires_human_true_with_empty_recommended_moves_is_rejected() -> None:
    with pytest.raises(ValidationError, match="requires_human=true requires recommended_moves"):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(observed_stage="DISCOVERY", objections=[], requires_human=True, recommended_moves=[])
        )


def test_requires_human_true_with_only_handoff_is_accepted() -> None:
    SalesTurnAnalysisOutput.model_validate(
        _valid_output(
            observed_stage="DISCOVERY", objections=[], requires_human=True, recommended_moves=["HANDOFF_TO_HUMAN"]
        )
    )


def test_handoff_to_human_forbidden_when_requires_human_is_false() -> None:
    with pytest.raises(ValidationError, match="HANDOFF_TO_HUMAN must not be recommended"):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(
                observed_stage="DISCOVERY",
                objections=[],
                requires_human=False,
                recommended_moves=["HANDOFF_TO_HUMAN"],
            )
        )


def test_callback_datetime_without_schedule_callback_move_is_rejected() -> None:
    with pytest.raises(ValidationError, match="SCHEDULE_CALLBACK is not in recommended_moves"):
        SalesTurnAnalysisOutput.model_validate(
            _valid_output(
                observed_stage="COMMITMENT",
                objections=[],
                recommended_moves=["ASK_FOR_COMMITMENT"],
                requested_callback_at="2026-09-07T15:00:00+00:00",
            )
        )


def test_callback_datetime_with_schedule_callback_move_is_accepted() -> None:
    SalesTurnAnalysisOutput.model_validate(
        _valid_output(
            observed_stage="COMMITMENT",
            objections=[],
            recommended_moves=["SCHEDULE_CALLBACK"],
            requested_callback_at="2026-09-07T15:00:00+00:00",
        )
    )
