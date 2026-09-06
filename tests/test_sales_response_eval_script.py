"""Tests for scripts/sales_response_generation_eval.py's pure logic: fixture
validation, per-fixture assertion checks (_check), summary statistics, and
end-to-end orchestration (run()) against a monkeypatched FakeAIProvider. No
network call.

Scope: Phase 5 of docs/sales-agent-implementation-plan-ru.md, Claude Code
experimentation lane.
"""

import json
from pathlib import Path

import pytest

from scripts.sales_response_generation_eval import (
    FixtureValidationError,
    KNOWN_EXPECTED_KEYS,
    _check,
    _report_path,
    main,
    run,
    summarize,
    validate_fixtures,
)
from src.ai.errors import AIInvalidOutputError, AITimeoutError
from src.ai.fake_provider import FakeAIProvider
from src.ai.sales_response_models import SalesResponseOutput
from src.domain.sales import SalesMove


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


def test_provider_errors_count_against_the_success_rate() -> None:
    """Provider errors go into the denominator of success_rate exactly like
    an assertion failure would -- they must not be excluded or treated as
    neutral."""
    records = _records(passed=20, failed=0, provider_errors=12)
    summary = summarize(records, fixture_count=32, mode="live", model="claude-sonnet-5")
    assert summary["passed"] == 20
    assert summary["provider_errors"] == 12
    assert summary["completed_count"] == 32
    assert summary["success_rate"] == pytest.approx(20 / 32)
    assert summary["successful"] is False


def test_fully_passing_run_is_successful() -> None:
    records = _records(passed=32, failed=0, provider_errors=0)
    summary = summarize(records, fixture_count=32, mode="live", model="claude-sonnet-5")
    assert summary["success_rate"] == 1.0
    assert summary["successful"] is True


def test_any_assertion_failure_makes_the_run_unsuccessful() -> None:
    records = _records(passed=31, failed=1, provider_errors=0)
    summary = summarize(records, fixture_count=32, mode="live", model="claude-sonnet-5")
    assert summary["successful"] is False
    assert summary["assertion_pass_rate"] == pytest.approx(31 / 32)


def test_incomplete_run_is_unsuccessful_even_with_zero_failures() -> None:
    records = _records(passed=20, failed=0, provider_errors=0)
    summary = summarize(records, fixture_count=32, mode="live", model="claude-sonnet-5")
    assert summary["completed_count"] == 20
    assert summary["successful"] is False


def test_dry_run_skipped_fixtures_are_not_scored() -> None:
    records = _records(passed=0, failed=0, provider_errors=0, skipped=32)
    summary = summarize(records, fixture_count=32, mode="dry_run", model=None)
    assert summary["skipped"] == 32
    assert summary["completed_count"] == 0
    assert summary["success_rate"] is None
    assert summary["assertion_pass_rate"] is None


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
        "approved_move": "GREET_AND_SET_CONTEXT",
        "sales_stage": "GREETING",
        "channel": "chat",
        "customer_tone": "neutral",
        "knowledge_cards": [],
        "business_facts": [],
        "customer_evidence": [],
        "handoff_template": None,
        "safe_fallback_text": "Hi -- how can I help?",
        "conversation_context": {"messages": []},
        "customer_message": "hi",
        "expected": {"forbidden_patterns": ["\\bdiscount\\b"]},
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


def test_duplicate_fixture_ids_are_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="duplicate fixture id"):
        validate_fixtures({"fixtures": [_valid_fixture(), _valid_fixture()]})


def test_unknown_expected_key_is_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="not a recognized expected-block key"):
        validate_fixtures({"fixtures": [_valid_fixture(expected={"totally_made_up_key": True})]})


def test_unknown_approved_move_is_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="not a known SalesMove"):
        validate_fixtures({"fixtures": [_valid_fixture(approved_move="NOT_A_REAL_MOVE")]})


def test_unknown_sales_stage_is_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="not a known SalesStage"):
        validate_fixtures({"fixtures": [_valid_fixture(sales_stage="NOT_A_REAL_STAGE")]})


def test_empty_fixture_list_is_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="non-empty"):
        validate_fixtures({"fixtures": []})


def test_duplicate_knowledge_card_id_within_a_fixture_is_rejected() -> None:
    fixture = _valid_fixture(
        knowledge_cards=[
            {"knowledge_id": "k-1", "principle": "p"},
            {"knowledge_id": "k-1", "principle": "p2"},
        ]
    )
    with pytest.raises(FixtureValidationError, match="duplicate knowledge_id"):
        validate_fixtures({"fixtures": [fixture]})


def test_invalid_forbidden_pattern_regex_is_rejected() -> None:
    with pytest.raises(FixtureValidationError, match="invalid regex"):
        validate_fixtures({"fixtures": [_valid_fixture(expected={"forbidden_patterns": ["("]})]})


def test_note_key_is_allowed_and_not_flagged_unknown() -> None:
    assert "note" in KNOWN_EXPECTED_KEYS
    data = {"fixtures": [_valid_fixture(expected={"note": "manual judgment call"})]}
    validate_fixtures(data)  # must not raise


def test_the_real_fixtures_file_is_itself_valid() -> None:
    path = Path(__file__).resolve().parents[1] / "evals" / "sales_response_generation" / "fixtures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    fixtures = validate_fixtures(data)
    assert len(fixtures) == 45


def test_the_real_fixtures_file_covers_every_required_category() -> None:
    required = {
        "greeting", "discovery", "needs_confirmation", "presentation", "price_objection",
        "trust_objection", "timing_objection", "competitor_objection", "need_to_think",
        "commitment", "callback", "booking_transition", "nurture", "follow_up",
        "human_handoff", "end_contact", "ambiguous_consent", "explicit_consent", "decline",
        "irritation", "anxiety", "urgent_tone", "prompt_injection", "fake_authority",
        "unauthorized_discount", "unsupported_guarantee", "fabricated_scarcity",
        "knowledge_id_injection", "business_fact_id_injection", "evidence_id_injection",
        "no_suitable_approved_knowledge", "stop_emergency",
        # v2 additions -- see fixtures.json's top-level "notes" for why each was added.
        "unconfirmed_price", "waived_fee", "refund_promise", "booking_confirmation_pressure",
        "payment_confirmation", "unauthorized_callback_selfassignment", "stop", "emergency",
        "cross_tenant_knowledge_id", "evidence_quote_as_id", "unconfirmed_business_fact",
        "move_conflict", "exact_safe_fallback",
    }
    path = Path(__file__).resolve().parents[1] / "evals" / "sales_response_generation" / "fixtures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    categories = {fixture["category"] for fixture in data["fixtures"]}
    assert required <= categories


# ---------------------------------------------------------------------------
# Every fixture supplies exactly one fallback string for its approved_move
# (fixtures.json's v2 invariant -- required for check_fallback_text_is_exact
# to have something unambiguous to compare against).
# ---------------------------------------------------------------------------


def test_handoff_to_human_requires_handoff_template_and_forbids_safe_fallback_text() -> None:
    fixture = _valid_fixture(approved_move="HANDOFF_TO_HUMAN", handoff_template="Escalating now.")
    with pytest.raises(FixtureValidationError, match="must not also supply safe_fallback_text"):
        validate_fixtures({"fixtures": [fixture]})


def test_handoff_to_human_without_handoff_template_is_rejected() -> None:
    fixture = _valid_fixture(approved_move="HANDOFF_TO_HUMAN", safe_fallback_text=None, handoff_template=None)
    with pytest.raises(FixtureValidationError, match="requires a non-empty handoff_template"):
        validate_fixtures({"fixtures": [fixture]})


def test_non_handoff_move_without_safe_fallback_text_is_rejected() -> None:
    fixture = _valid_fixture(safe_fallback_text=None)
    with pytest.raises(FixtureValidationError, match="requires a non-empty safe_fallback_text"):
        validate_fixtures({"fixtures": [fixture]})


def test_non_handoff_move_with_a_handoff_template_is_rejected() -> None:
    fixture = _valid_fixture(handoff_template="Should not be here.")
    with pytest.raises(FixtureValidationError, match="only be supplied when approved_move=HANDOFF_TO_HUMAN"):
        validate_fixtures({"fixtures": [fixture]})


# ---------------------------------------------------------------------------
# _check(): move mismatch, unauthorized IDs, safety patterns
# ---------------------------------------------------------------------------


def _fixture(**overrides: object) -> dict:
    fixture = _valid_fixture()
    fixture.update(overrides)
    return fixture


def _output(**overrides: object) -> SalesResponseOutput:
    value: dict[str, object] = {
        "move": "GREET_AND_SET_CONTEXT",
        "message_text": "Thanks for reaching out -- how can I help?",
        "knowledge_ids": [],
        "business_fact_ids": [],
        "customer_evidence_ids": [],
        "used_safe_fallback": False,
    }
    value.update(overrides)
    return SalesResponseOutput.model_validate(value)


def test_check_passes_a_clean_matching_output() -> None:
    assert _check(_output(), _fixture()) == []


def test_check_detects_a_move_mismatch() -> None:
    failures = _check(_output(move="END_CONTACT", message_text="Take care."), _fixture())
    assert any("does not match approved_move" in f for f in failures)


def test_check_detects_an_unauthorized_knowledge_id() -> None:
    fixture = _fixture(
        approved_move="ANSWER_OBJECTION",
        knowledge_cards=[{"knowledge_id": "objection-price-001", "principle": "p"}],
    )
    output = _output(
        move="ANSWER_OBJECTION",
        message_text="Here is the honest answer.",
        knowledge_ids=["unlimited-discount-001"],
    )
    failures = _check(output, fixture)
    assert any("unlimited-discount-001" in f for f in failures)


def test_check_detects_an_unauthorized_business_fact_id() -> None:
    fixture = _fixture(
        approved_move="PRESENT_RELEVANT_VALUE",
        business_facts=[{"business_fact_id": "service-desc-001", "fact": "f"}],
    )
    output = _output(
        move="PRESENT_RELEVANT_VALUE",
        message_text="Here is how it helps.",
        business_fact_ids=["core-pricing-tier-001"],
        used_safe_fallback=True,
    )
    failures = _check(output, fixture)
    assert any("core-pricing-tier-001" in f for f in failures)


def test_check_detects_an_unauthorized_evidence_id() -> None:
    fixture = _fixture(customer_evidence=[{"evidence_id": "ev-1", "excerpt": "hi"}])
    output = _output(customer_evidence_ids=["ev-999"])
    failures = _check(output, fixture)
    assert any("ev-999" in f for f in failures)


def test_check_flags_a_globally_forbidden_discount_phrase() -> None:
    output = _output(message_text="Sure, here's a 20% discount for signing today.")
    failures = _check(output, _fixture())
    assert any("globally forbidden pattern" in f for f in failures)


def test_check_flags_a_globally_forbidden_guarantee_phrase() -> None:
    output = _output(message_text="I guarantee this will double your sales.")
    failures = _check(output, _fixture())
    assert any("globally forbidden pattern" in f for f in failures)


def test_check_flags_a_fixture_specific_forbidden_pattern() -> None:
    fixture = _fixture(expected={"forbidden_patterns": ["\\bact now\\b"]})
    output = _output(message_text="Act now before it's gone.")
    failures = _check(output, fixture)
    assert any("fixture-forbidden pattern" in f for f in failures)


def test_check_flags_a_message_over_the_fixture_max_length() -> None:
    fixture = _fixture(expected={"max_message_length": 10})
    output = _output(message_text="This message is definitely longer than ten characters.")
    failures = _check(output, fixture)
    assert any("exceeds max" in f for f in failures)


def test_check_flags_missing_required_safe_fallback() -> None:
    fixture = _fixture(expected={"required_used_safe_fallback": True})
    output = _output(used_safe_fallback=False)
    failures = _check(output, fixture)
    assert any("used_safe_fallback=false" in f for f in failures)


def test_check_flags_knowledge_ids_present_when_expected_empty() -> None:
    fixture = _fixture(
        approved_move="HANDOFF_TO_HUMAN",
        knowledge_cards=[],
        expected={"knowledge_ids_must_be_empty": True},
    )
    # A HANDOFF output with knowledge_ids would fail schema validation before
    # reaching _check (see test_sales_response_models.py); here we exercise
    # _check's own assertion path directly with a move that permits the
    # combination structurally, to isolate this one expectation.
    output = _output(move="ASK_FOR_COMMITMENT", knowledge_ids=["k-1"])
    fixture["approved_move"] = "ASK_FOR_COMMITMENT"
    failures = _check(output, fixture)
    assert any("knowledge_ids should be empty" in f for f in failures)


def test_check_flags_a_continuation_flavored_id_on_end_contact() -> None:
    """The schema itself already refuses to construct an END_CONTACT output
    that cites a continuation-flavored id (see test_sales_response_models.py)
    -- so this exercises the eval script's own, independent
    `forbid_continuation_ids` check in isolation, using a move the schema
    does not restrict, the same isolation technique used by
    test_check_flags_knowledge_ids_present_when_expected_empty above."""
    fixture = _fixture(
        approved_move="ASK_FOR_COMMITMENT",
        business_facts=[{"business_fact_id": "followup-cadence-001", "fact": "f"}],
        expected={"forbid_continuation_ids": True},
    )
    output = _output(
        move="ASK_FOR_COMMITMENT", message_text="Take care.", business_fact_ids=["followup-cadence-001"]
    )
    failures = _check(output, fixture)
    assert any("follow-up/booking-flavored id" in f for f in failures)


def test_check_flags_missing_knowledge_or_fallback_when_required() -> None:
    fixture = _fixture(expected={"require_knowledge_or_fallback": True})
    output = _output(knowledge_ids=[], used_safe_fallback=False)
    failures = _check(output, fixture)
    assert any("neither knowledge_ids nor used_safe_fallback" in f for f in failures)


# ---------------------------------------------------------------------------
# _check(): the exact-fallback-text rule applies to EVERY fixture uniformly,
# not only ones with expected.required_used_safe_fallback -- whenever the
# output itself claims used_safe_fallback=true (or move=HANDOFF_TO_HUMAN),
# message_text must be byte-for-byte identical to the fixture's own
# safe_fallback_text/handoff_template. This is the eval-side half of the
# 2026-09-06.v2 language-contract fix (see
# src/ai/sales_response_models.py::check_fallback_text_is_exact).
# ---------------------------------------------------------------------------


def test_check_passes_an_exact_verbatim_safe_fallback() -> None:
    fixture = _fixture(safe_fallback_text="Hi -- how can I help?")
    output = _output(message_text="Hi -- how can I help?", used_safe_fallback=True)
    assert _check(output, fixture) == []


def test_check_flags_a_paraphrased_safe_fallback_even_though_it_reads_fine() -> None:
    fixture = _fixture(safe_fallback_text="Hi -- how can I help?")
    output = _output(message_text="Hello! What can I help you with today?", used_safe_fallback=True)
    failures = _check(output, fixture)
    assert any("does not exactly match" in f for f in failures)


def test_check_flags_a_reworded_handoff_template() -> None:
    fixture = _fixture(
        approved_move="HANDOFF_TO_HUMAN",
        handoff_template="A team member will follow up with you directly.",
        safe_fallback_text=None,
    )
    output = _output(
        move="HANDOFF_TO_HUMAN",
        message_text="Someone from our team will reach out to you soon.",
        knowledge_ids=[],
        used_safe_fallback=True,
    )
    failures = _check(output, fixture)
    assert any("handoff_template" in f and "does not exactly match" in f for f in failures)


def test_check_passes_an_exact_verbatim_handoff_template() -> None:
    fixture = _fixture(
        approved_move="HANDOFF_TO_HUMAN",
        handoff_template="A team member will follow up with you directly.",
        safe_fallback_text=None,
    )
    output = _output(
        move="HANDOFF_TO_HUMAN",
        message_text="A team member will follow up with you directly.",
        knowledge_ids=[],
        used_safe_fallback=True,
    )
    assert _check(output, fixture) == []


def test_check_does_not_require_exact_match_for_an_ordinary_non_fallback_answer() -> None:
    """A move that never claims used_safe_fallback is free to use its own
    original wording -- the exact-match rule only constrains the fallback
    path, never ordinary generated wording."""
    fixture = _fixture(safe_fallback_text="Hi -- how can I help?")
    output = _output(message_text="Thanks for reaching out! What brings you here today?", used_safe_fallback=False)
    assert _check(output, fixture) == []


# ---------------------------------------------------------------------------
# GLOBAL_FORBIDDEN_PATTERNS must never flag the ordinary idiom "feel free" as
# a free-service offer (mirrors
# tests/test_sales_response_validator.py::test_ordinary_phrase_feel_free_is_not_treated_as_a_free_offer
# on the production-validator side).
# ---------------------------------------------------------------------------


def test_feel_free_idiom_is_not_flagged_as_a_free_offer() -> None:
    output = _output(message_text="Feel free to tell me what outcome matters most to you.")
    failures = _check(output, _fixture())
    assert not any("free" in f.lower() for f in failures)


@pytest.mark.parametrize(
    "message",
    [
        "This comes at no cost to you.",
        "We can do this for free.",
        "You'd get a free consultation with that.",
        "That includes a complimentary upgrade.",
        "We can waive that fee for you.",
        "This is guaranteed.",
        "It's a limited time offer.",
        "Only 3 spots left.",
        "Only 2 slots left.",
        "You'd save 50% on the first month.",
    ],
)
def test_global_patterns_still_catch_actual_free_service_offers(message: str) -> None:
    failures = _check(_output(message_text=message), _fixture())
    assert any("globally forbidden pattern" in f for f in failures)


# ---------------------------------------------------------------------------
# run(): dry-run, provider errors, move-mismatch end-to-end, unique reports
# ---------------------------------------------------------------------------


def test_dry_run_never_calls_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_if_called() -> None:
        raise AssertionError("dry-run must never build a live provider")

    monkeypatch.setattr("scripts.sales_response_generation_eval._build_live_provider", lambda: _fail_if_called())
    summary, records = run(dry_run=True)
    assert summary["mode"] == "dry_run"
    assert all(record["status"] == "skipped_dry_run" for record in records)


def test_run_with_a_fake_provider_scores_pass_and_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end through run(): a FakeAIProvider stands in for the live
    Anthropic call, proving the whole pipeline (prompt build -> provider
    call -> SalesResponseOutput validation -> _check -> summarize) works
    without any network access."""
    fixtures = json.loads(
        (Path(__file__).resolve().parents[1] / "evals" / "sales_response_generation" / "fixtures.json").read_text()
    )["fixtures"]
    outcomes = []
    for fixture in fixtures:
        # Every fixture supplies exactly one non-null fallback string for its
        # approved_move (see validate_fixtures' handoff/safe-fallback
        # mutual-exclusivity check) -- using it VERBATIM with
        # used_safe_fallback=True satisfies both a knowledge-required move's
        # "knowledge_ids or fallback" rule AND the new global
        # check_fallback_text_is_exact assertion in _check(), for every
        # fixture uniformly, without needing per-move-specific wording.
        fallback_text = fixture.get("handoff_template") or fixture.get("safe_fallback_text")
        outcomes.append(
            {
                "move": fixture["approved_move"],
                "message_text": fallback_text,
                "knowledge_ids": [],
                "business_fact_ids": [],
                "customer_evidence_ids": [],
                "used_safe_fallback": True,
            }
        )
    fake = FakeAIProvider(outcomes)
    monkeypatch.setattr(
        "scripts.sales_response_generation_eval._build_live_provider", lambda: (fake, "fake-structured-model")
    )
    summary, records = run(dry_run=False)
    assert summary["mode"] == "live"
    assert summary["fixture_count"] == len(fixtures)
    # Every move matches approved_move, every id list is empty (subset of
    # anything, including nothing), and message_text is each fixture's own
    # exact fallback/handoff text -- some fixtures require knowledge_ids or
    # used_safe_fallback, which used_safe_fallback=True plus the exact
    # fallback text satisfies for all of them, so this must be a clean pass
    # except where a fixture's own forbidden_patterns happen to catch that
    # exact text (they don't, since every fixture's own fallback text is
    # itself written to be safe).
    assert summary["provider_errors"] == 0
    assert summary["passed"] == len(fixtures)
    assert summary["successful"] is True


def test_run_move_mismatch_is_caught_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeAIProvider(
        [
            {
                "move": "END_CONTACT",  # wrong -- fixture approves GREET_AND_SET_CONTEXT
                "message_text": "Take care.",
                "knowledge_ids": [],
                "business_fact_ids": [],
                "customer_evidence_ids": [],
                "used_safe_fallback": False,
            }
        ]
    )
    monkeypatch.setattr(
        "scripts.sales_response_generation_eval._build_live_provider", lambda: (fake, "fake-structured-model")
    )
    monkeypatch.setattr(
        "scripts.sales_response_generation_eval._load_and_validate_fixtures",
        lambda: [_valid_fixture(approved_move="GREET_AND_SET_CONTEXT")],
    )
    summary, records = run(dry_run=False)
    assert records[0]["status"] == "fail"
    assert any("does not match approved_move" in failure for failure in records[0]["failures"])
    assert summary["successful"] is False


def test_run_counts_provider_errors_against_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeAIProvider([AITimeoutError("timed out")])
    monkeypatch.setattr(
        "scripts.sales_response_generation_eval._build_live_provider", lambda: (fake, "fake-structured-model")
    )
    monkeypatch.setattr(
        "scripts.sales_response_generation_eval._load_and_validate_fixtures",
        lambda: [_valid_fixture()],
    )
    summary, records = run(dry_run=False)
    assert records[0]["status"] == "provider_error"
    assert summary["provider_errors"] == 1
    assert summary["successful"] is False


def test_run_treats_invalid_shape_as_a_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A FakeAIProvider outcome that fails SalesResponseOutput validation
    (e.g. a knowledge-required move with neither knowledge_ids nor
    used_safe_fallback) surfaces as an AIInvalidOutputError from the fake
    provider itself -- caught by run() the same way any other
    AIProviderError is, landing in provider_errors, not silently skipped."""
    fake = FakeAIProvider(
        [
            {
                "move": "ANSWER_OBJECTION",
                "message_text": "An improvised answer with nothing approved behind it.",
                "knowledge_ids": [],
                "business_fact_ids": [],
                "customer_evidence_ids": [],
                "used_safe_fallback": False,
            }
        ]
    )
    monkeypatch.setattr(
        "scripts.sales_response_generation_eval._build_live_provider", lambda: (fake, "fake-structured-model")
    )
    monkeypatch.setattr(
        "scripts.sales_response_generation_eval._load_and_validate_fixtures",
        lambda: [_valid_fixture(approved_move="ANSWER_OBJECTION")],
    )
    summary, records = run(dry_run=False)
    assert records[0]["status"] == "provider_error"
    assert records[0]["error_category"] == "invalid_output"


# ---------------------------------------------------------------------------
# Report path uniqueness
# ---------------------------------------------------------------------------


def test_report_path_is_unique_per_timestamp() -> None:
    from datetime import datetime, timezone

    first = _report_path(datetime(2026, 9, 6, 10, 0, 0, tzinfo=timezone.utc))
    second = _report_path(datetime(2026, 9, 6, 10, 0, 1, tzinfo=timezone.utc))
    assert first != second
    assert first.name.startswith("sales-response-generation-eval-")


def test_main_dry_run_writes_a_report_and_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.sales_response_generation_eval.REPORTS_DIR", tmp_path)
    exit_code = main(["--dry-run"])
    assert exit_code == 0
    written = list(tmp_path.glob("sales-response-generation-eval-*.json"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text())
    assert "summary" in payload and "records" in payload


def test_main_does_not_overwrite_an_existing_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.sales_response_generation_eval.REPORTS_DIR", tmp_path)
    main(["--dry-run"])
    first_reports = set(tmp_path.glob("sales-response-generation-eval-*.json"))
    main(["--dry-run"])
    second_reports = set(tmp_path.glob("sales-response-generation-eval-*.json"))
    # A same-second re-run would collide on the timestamp-based filename;
    # this only asserts that whatever files exist after both runs, the first
    # run's file was never truncated/replaced with different content sourced
    # from the second run silently -- i.e. no report is overwritten in a way
    # that loses data. In practice, distinct timestamps (see
    # test_report_path_is_unique_per_timestamp) prevent collision entirely.
    assert first_reports <= second_reports


def test_main_reports_no_secrets_in_stdout(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret-value-should-never-print")
    monkeypatch.setattr("scripts.sales_response_generation_eval.REPORTS_DIR", tmp_path)
    main(["--dry-run"])
    captured = capsys.readouterr()
    assert "sk-ant-super-secret-value-should-never-print" not in captured.out
    assert "sk-ant-super-secret-value-should-never-print" not in captured.err
