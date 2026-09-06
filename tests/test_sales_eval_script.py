"""Tests for scripts/sales_turn_analysis_eval.py's pure logic: summary
statistics and fixtures.json validation. No provider call, no network.

Scope: docs/agent-prompts/claude-code-sales-knowledge-and-evals.md,
2026-09-06 code-review pass, items 1 and 7.
"""

import json

import pytest

from scripts.sales_turn_analysis_eval import (
    FixtureValidationError,
    KNOWN_EXPECTED_KEYS,
    summarize,
    validate_fixtures,
)


# ---------------------------------------------------------------------------
# summarize()
# ---------------------------------------------------------------------------


def _records(*, passed: int, failed: int, provider_errors: int, skipped: int = 0) -> list[dict]:
    records = []
    for i in range(passed):
        records.append({"id": f"pass-{i}", "category": "c", "status": "pass"})
    for i in range(failed):
        records.append({"id": f"fail-{i}", "category": "c", "status": "fail"})
    for i in range(provider_errors):
        records.append({"id": f"error-{i}", "category": "c", "status": "provider_error"})
    for i in range(skipped):
        records.append({"id": f"skip-{i}", "category": "c", "status": "skipped_dry_run"})
    return records


def test_provider_errors_no_longer_inflate_the_success_rate() -> None:
    """The exact regression this task was opened for: 15 pass, 9
    provider_error, out of 24 fixtures -- must report 0.625, not 1.0, and
    must not be considered successful."""
    records = _records(passed=15, failed=0, provider_errors=9)
    summary = summarize(records, fixture_count=24, mode="live", model="claude-sonnet-5")
    assert summary["passed"] == 15
    assert summary["assertion_failed"] == 0
    assert summary["provider_errors"] == 9
    assert summary["completed_count"] == 24
    assert summary["success_rate"] == pytest.approx(0.625)
    assert summary["successful"] is False


def test_fully_passing_run_is_successful() -> None:
    records = _records(passed=24, failed=0, provider_errors=0)
    summary = summarize(records, fixture_count=24, mode="live", model="claude-sonnet-5")
    assert summary["success_rate"] == 1.0
    assert summary["successful"] is True


def test_any_assertion_failure_makes_the_run_unsuccessful_even_with_no_errors() -> None:
    records = _records(passed=23, failed=1, provider_errors=0)
    summary = summarize(records, fixture_count=24, mode="live", model="claude-sonnet-5")
    assert summary["completed_count"] == 24
    assert summary["successful"] is False
    assert summary["success_rate"] == pytest.approx(23 / 24)
    assert summary["assertion_pass_rate"] == pytest.approx(23 / 24)


def test_incomplete_run_is_unsuccessful_even_with_zero_failures_and_errors() -> None:
    """completed_count < fixture_count (e.g. a bug that silently drops a
    fixture from the loop) must not be reported as successful just because
    nothing failed among the ones that did run."""
    records = _records(passed=20, failed=0, provider_errors=0)
    summary = summarize(records, fixture_count=24, mode="live", model="claude-sonnet-5")
    assert summary["completed_count"] == 20
    assert summary["successful"] is False


def test_dry_run_skipped_fixtures_are_not_scored_and_rates_are_none() -> None:
    records = _records(passed=0, failed=0, provider_errors=0, skipped=24)
    summary = summarize(records, fixture_count=24, mode="dry_run", model=None)
    assert summary["skipped"] == 24
    assert summary["completed_count"] == 0
    assert summary["success_rate"] is None
    assert summary["assertion_pass_rate"] is None
    # successful=False is fine here -- main() never uses "successful" to
    # decide a dry-run's exit code (see test_dry_run_exit_code below and
    # scripts/sales_turn_analysis_eval.py::main).
    assert summary["successful"] is False


def test_assertion_pass_rate_ignores_provider_errors() -> None:
    records = _records(passed=3, failed=1, provider_errors=5)
    summary = summarize(records, fixture_count=9, mode="live", model="m")
    assert summary["assertion_pass_rate"] == pytest.approx(3 / 4)


def test_by_category_excludes_skipped_dry_run() -> None:
    records = [
        {"id": "a", "category": "greeting", "status": "pass"},
        {"id": "b", "category": "greeting", "status": "skipped_dry_run"},
    ]
    summary = summarize(records, fixture_count=2, mode="dry_run", model=None)
    assert summary["by_category"] == {"greeting": {"cases": 1, "passed": 1}}


# ---------------------------------------------------------------------------
# validate_fixtures()
# ---------------------------------------------------------------------------


def _valid_fixture(**overrides: object) -> dict:
    fixture = {
        "id": "greeting-001",
        "category": "greeting",
        "customer_message": "hi",
        "profile_context": {"stage": "GREETING"},
        "conversation_context": {"messages": []},
        "expected": {"observed_stage_in": ["GREETING"], "requires_human": False},
    }
    fixture.update(overrides)
    return fixture


def test_valid_fixtures_pass_through_unchanged() -> None:
    data = {"fixtures": [_valid_fixture()]}
    assert validate_fixtures(data) == data["fixtures"]


def test_missing_required_key_is_rejected() -> None:
    fixture = _valid_fixture()
    del fixture["customer_message"]
    with pytest.raises(FixtureValidationError, match="customer_message"):
        validate_fixtures({"fixtures": [fixture]})


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="duplicate fixture id"):
        validate_fixtures({"fixtures": [_valid_fixture(), _valid_fixture()]})


def test_unknown_expected_key_is_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="not a recognized expected-block key"):
        validate_fixtures({"fixtures": [_valid_fixture(expected={"totally_made_up_key": True})]})


def test_unknown_enum_value_in_expected_is_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="unknown SalesStage value"):
        validate_fixtures({"fixtures": [_valid_fixture(expected={"observed_stage_in": ["NOT_A_REAL_STAGE"]})]})


def test_empty_fixture_list_is_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="non-empty"):
        validate_fixtures({"fixtures": []})


def test_missing_fixtures_key_is_rejected() -> None:
    with pytest.raises(FixtureValidationError):
        validate_fixtures({"not_fixtures": []})


def test_note_key_is_allowed_and_not_flagged_unknown() -> None:
    assert "note" in KNOWN_EXPECTED_KEYS
    data = {"fixtures": [_valid_fixture(expected={"note": "manual judgment call"})]}
    validate_fixtures(data)  # must not raise


def test_min_confidence_out_of_range_is_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="min_confidence"):
        validate_fixtures({"fixtures": [_valid_fixture(expected={"min_confidence": 1.5})]})


def test_the_real_fixtures_file_is_itself_valid() -> None:
    """The shipped evals/sales_turn_analysis/fixtures.json must pass its own
    schema -- this is what --dry-run actually exercises."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "evals" / "sales_turn_analysis" / "fixtures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    fixtures = validate_fixtures(data)
    assert len(fixtures) == 24
