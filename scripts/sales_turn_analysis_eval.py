"""Run the experimental SalesTurnAnalysis prompt against evals/sales_turn_analysis/fixtures.json.

Part C of docs/agent-prompts/claude-code-sales-knowledge-and-evals.md. Mirrors
the shape of scripts/live_vertical_eval.py: synthetic fixtures, the project's
normal AI configuration (Settings.from_environment()), no persistence, no
customer-facing side effects. Never reads or prints ANTHROPIC_API_KEY itself
-- it only passes Settings.anthropic_api_key straight into the SDK client,
exactly like src/ai/runtime.py does.

Does not touch SalesPolicyEngine, ProcessState, migrations, the API, or
frontend code. It does not construct real src.domain.sales.SalesTurnAnalysis
objects during scoring either -- see src/ai/sales_adapter.py for that
conversion (used here only for its evidence-grounding check, reused rather
than duplicated); wiring the adapter's domain-object construction into this
script is out of this task's scope.

Exit codes:
    0 -- dry-run with valid fixtures (regardless of what dry-run validates),
         or a live run where every fixture completed with no assertion
         failures and no provider errors (summary["successful"] is true).
    1 -- a live run that completed but was not fully successful (some
         fixture failed its assertions, hit a provider error, or -- should
         not happen, since every fixture is always attempted -- did not
         reach a terminal status).
    2 -- the fixtures file itself is invalid (bad shape, duplicate ids,
         unknown `expected` keys, unknown enum values, empty fixture list).
         This check runs BEFORE any provider call, in both dry-run and live
         mode, so a broken fixtures file is caught without spending an API
         call.

Usage:
    docker compose run --rm app python scripts/sales_turn_analysis_eval.py
    docker compose run --rm app python scripts/sales_turn_analysis_eval.py --dry-run
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Mapping

from src.ai.errors import AIProviderError
from src.ai.models import AIRequest
from src.ai.provider import RetryingAIProvider
from src.ai.anthropic_provider import AnthropicProvider
from src.ai.sales_adapter import check_evidence_grounded
from src.ai.sales_models import SALES_PROMPT_VERSION, SalesTurnAnalysisOutput
from src.ai.sales_prompts import sales_turn_analysis_prompt
from src.config import Settings
from src.domain.sales import CommitmentLevel, ObjectionStatus, ObjectionType, SalesMove, SalesStage


ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "evals" / "sales_turn_analysis" / "fixtures.json"
REPORTS_DIR = ROOT / "reports"

# Every key an `expected` block may use. Kept as a single source of truth so
# _validate_fixtures and the docs stay in sync; "note" carries no scoring
# logic, it is documentation for a human reading the fixture.
KNOWN_EXPECTED_KEYS = frozenset({
    "observed_stage_in",
    "commitment_level_in",
    "commitment_level_forbidden",
    "allowed_recommended_moves",
    "forbidden_moves",
    "requires_human",
    "required_objection_types",
    "objection_status_in",
    "objection_cause_must_be_null",
    "requested_callback_at_must_be_null",
    "min_confidence",
    "min_signal_count",
    "customer_intent_must_not_contain",
    "note",
})

_REQUIRED_FIXTURE_KEYS = ("id", "category", "customer_message", "profile_context", "conversation_context")


class FixtureValidationError(ValueError):
    """The fixtures file itself is malformed. Raised before any provider
    call -- both --dry-run and a live run must catch a bad fixtures file
    without spending an API request."""


def _validate_enum_list(fixture_id: str, key: str, values: Any, enum_cls: type) -> list[str]:
    if not isinstance(values, list):
        return [f"{fixture_id}: expected.{key} must be a list"]
    issues = []
    valid = {member.value for member in enum_cls}
    for value in values:
        if value not in valid:
            issues.append(f"{fixture_id}: expected.{key} contains unknown {enum_cls.__name__} value {value!r}")
    return issues


def _validate_expected_block(fixture_id: str, expected: Any) -> list[str]:
    if expected is None:
        return []
    if not isinstance(expected, dict):
        return [f"{fixture_id}: 'expected' must be an object"]
    issues: list[str] = []
    unknown = set(expected) - KNOWN_EXPECTED_KEYS
    for key in sorted(unknown):
        issues.append(f"{fixture_id}: expected.{key!r} is not a recognized expected-block key")

    if "observed_stage_in" in expected:
        issues += _validate_enum_list(fixture_id, "observed_stage_in", expected["observed_stage_in"], SalesStage)
    for key in ("commitment_level_in", "commitment_level_forbidden"):
        if key in expected:
            issues += _validate_enum_list(fixture_id, key, expected[key], CommitmentLevel)
    for key in ("allowed_recommended_moves", "forbidden_moves"):
        if key in expected:
            issues += _validate_enum_list(fixture_id, key, expected[key], SalesMove)
    if "required_objection_types" in expected:
        issues += _validate_enum_list(fixture_id, "required_objection_types", expected["required_objection_types"], ObjectionType)
    if "objection_status_in" in expected:
        issues += _validate_enum_list(fixture_id, "objection_status_in", expected["objection_status_in"], ObjectionStatus)

    if "requires_human" in expected and expected["requires_human"] is not None and not isinstance(expected["requires_human"], bool):
        issues.append(f"{fixture_id}: expected.requires_human must be true, false, or null")
    for key in ("objection_cause_must_be_null", "requested_callback_at_must_be_null"):
        if key in expected and not isinstance(expected[key], bool):
            issues.append(f"{fixture_id}: expected.{key} must be a boolean")
    if "min_confidence" in expected:
        value = expected["min_confidence"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 <= value <= 1.0:
            issues.append(f"{fixture_id}: expected.min_confidence must be a number between 0 and 1")
    if "min_signal_count" in expected:
        value = expected["min_signal_count"]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            issues.append(f"{fixture_id}: expected.min_signal_count must be a non-negative integer")
    if "customer_intent_must_not_contain" in expected:
        value = expected["customer_intent_must_not_contain"]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            issues.append(f"{fixture_id}: expected.customer_intent_must_not_contain must be a list of strings")
    if "note" in expected and not isinstance(expected["note"], str):
        issues.append(f"{fixture_id}: expected.note must be a string")
    return issues


def validate_fixtures(data: Any) -> list[dict[str, Any]]:
    """Raise FixtureValidationError with every problem found, or return the
    fixture list. Runs entirely offline -- no provider call, no network."""
    if not isinstance(data, dict) or "fixtures" not in data:
        raise FixtureValidationError("fixtures file must be a JSON object with a top-level 'fixtures' list")
    fixtures = data["fixtures"]
    if not isinstance(fixtures, list) or len(fixtures) == 0:
        raise FixtureValidationError("'fixtures' must be a non-empty list")

    issues: list[str] = []
    seen_ids: set[str] = set()
    for index, fixture in enumerate(fixtures):
        label = f"fixtures[{index}]"
        if not isinstance(fixture, dict):
            issues.append(f"{label}: each fixture must be an object")
            continue
        fixture_id = fixture.get("id")
        label = fixture_id if isinstance(fixture_id, str) and fixture_id else label

        for key in _REQUIRED_FIXTURE_KEYS:
            if key not in fixture:
                issues.append(f"{label}: missing required key {key!r}")
        if isinstance(fixture_id, str):
            if not fixture_id.strip():
                issues.append(f"{label}: 'id' must not be blank")
            elif fixture_id in seen_ids:
                issues.append(f"duplicate fixture id {fixture_id!r}")
            else:
                seen_ids.add(fixture_id)
        elif "id" in fixture:
            issues.append(f"{label}: 'id' must be a string")
        for key in ("category", "customer_message"):
            if key in fixture and (not isinstance(fixture[key], str) or not fixture[key].strip()):
                issues.append(f"{label}: {key!r} must be a non-empty string")
        for key in ("profile_context", "conversation_context"):
            if key in fixture and not isinstance(fixture[key], dict):
                issues.append(f"{label}: {key!r} must be an object")

        issues += _validate_expected_block(label, fixture.get("expected"))

    if issues:
        raise FixtureValidationError("invalid evals/sales_turn_analysis/fixtures.json:\n  " + "\n  ".join(issues))
    return fixtures


def _load_and_validate_fixtures(path: Path = FIXTURES_PATH) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    return validate_fixtures(data)


def _build_live_provider() -> tuple[RetryingAIProvider, str] | None:
    """Returns (provider, model) if Anthropic credentials are already
    configured through the project's normal runtime, else None (dry-run)."""
    try:
        settings = Settings.from_environment()
    except RuntimeError:
        return None
    if settings.ai_provider != "anthropic":
        return None
    if not settings.anthropic_api_key or not settings.anthropic_model:
        return None
    provider = RetryingAIProvider(
        AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            timeout_seconds=settings.ai_timeout_seconds,
        ),
        max_retries=settings.ai_max_retries,
    )
    return provider, settings.anthropic_model


def _check(output: SalesTurnAnalysisOutput, customer_message: str, expected: Mapping[str, Any]) -> list[str]:
    # Evidence grounding is the one check every fixture gets regardless of
    # its own `expected` block -- reused from src/ai/sales_adapter.py so
    # there is exactly one implementation of this rule in the codebase.
    failures = list(check_evidence_grounded(output, customer_message))

    if "observed_stage_in" in expected:
        allowed = {SalesStage(value) for value in expected["observed_stage_in"]}
        if output.observed_stage not in allowed:
            failures.append(f"observed_stage={output.observed_stage.value} not in {sorted(v.value for v in allowed)}")

    if "commitment_level_in" in expected:
        allowed = {CommitmentLevel(value) for value in expected["commitment_level_in"]}
        if output.commitment_level not in allowed:
            failures.append(f"commitment_level={output.commitment_level.value} not in {sorted(v.value for v in allowed)}")

    if "commitment_level_forbidden" in expected:
        forbidden = {CommitmentLevel(value) for value in expected["commitment_level_forbidden"]}
        if output.commitment_level in forbidden:
            failures.append(f"commitment_level={output.commitment_level.value} is forbidden")

    if "allowed_recommended_moves" in expected and output.recommended_moves:
        allowed = {SalesMove(value) for value in expected["allowed_recommended_moves"]}
        if not set(output.recommended_moves) & allowed:
            failures.append(
                f"recommended_moves={[m.value for m in output.recommended_moves]} does not intersect allowed {sorted(v.value for v in allowed)}"
            )

    if "forbidden_moves" in expected:
        forbidden = {SalesMove(value) for value in expected["forbidden_moves"]}
        hit = set(output.recommended_moves) & forbidden
        if hit:
            failures.append(f"recommended_moves contains forbidden {[m.value for m in hit]}")

    if expected.get("requires_human") is not None:
        if output.requires_human != expected["requires_human"]:
            failures.append(f"requires_human={output.requires_human}, expected {expected['requires_human']}")

    if "required_objection_types" in expected:
        expected_types = {ObjectionType(value) for value in expected["required_objection_types"]}
        actual_types = {objection.objection_type for objection in output.objections}
        missing = expected_types - actual_types
        if missing:
            failures.append(f"missing expected objection types {sorted(v.value for v in missing)}")

    if "objection_status_in" in expected and output.objections:
        allowed_statuses = set(expected["objection_status_in"])
        for objection in output.objections:
            if objection.status.value not in allowed_statuses:
                failures.append(f"objection status {objection.status.value} not in {allowed_statuses}")

    if expected.get("objection_cause_must_be_null") and output.objections:
        for objection in output.objections:
            if objection.cause is not None:
                failures.append(f"objection cause should be null, got {objection.cause!r}")

    if expected.get("requested_callback_at_must_be_null") and output.requested_callback_at is not None:
        failures.append(f"requested_callback_at should be null, got {output.requested_callback_at!r}")

    if "min_confidence" in expected and output.confidence < expected["min_confidence"]:
        failures.append(f"confidence={output.confidence} below min {expected['min_confidence']}")

    if "min_signal_count" in expected and len(output.signals) < expected["min_signal_count"]:
        failures.append(f"only {len(output.signals)} signals, expected at least {expected['min_signal_count']}")

    if "customer_intent_must_not_contain" in expected and output.customer_intent:
        lowered = output.customer_intent.lower()
        for banned in expected["customer_intent_must_not_contain"]:
            if banned.lower() in lowered:
                failures.append(f"customer_intent leaks banned phrase {banned!r}")

    return failures


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def summarize(records: list[dict[str, Any]], *, fixture_count: int, mode: str, model: str | None) -> dict[str, Any]:
    """Pure summary calculation -- no provider call, no filesystem access.
    Every fixture's `status` is exactly one of "pass", "fail",
    "provider_error", or "skipped_dry_run" (assigned by the caller's loop);
    this function does not itself call the provider or mutate `records`.
    """
    passed = sum(1 for r in records if r["status"] == "pass")
    assertion_failed = sum(1 for r in records if r["status"] == "fail")
    provider_errors = sum(1 for r in records if r["status"] == "provider_error")
    skipped = sum(1 for r in records if r["status"] == "skipped_dry_run")
    completed_count = passed + assertion_failed + provider_errors

    success_rate = (passed / completed_count) if completed_count else None
    assertion_pass_rate = (passed / (passed + assertion_failed)) if (passed + assertion_failed) else None
    successful = provider_errors == 0 and assertion_failed == 0 and completed_count == fixture_count

    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "model": model,
        "prompt_version": SALES_PROMPT_VERSION,
        "fixture_count": fixture_count,
        "passed": passed,
        "assertion_failed": assertion_failed,
        "provider_errors": provider_errors,
        "skipped": skipped,
        "completed_count": completed_count,
        "success_rate": success_rate,
        "assertion_pass_rate": assertion_pass_rate,
        "successful": successful,
        "by_category": {},
    }
    for record in records:
        if record["status"] not in {"pass", "fail", "provider_error"}:
            continue
        bucket = summary["by_category"].setdefault(record["category"], {"cases": 0, "passed": 0})
        bucket["cases"] += 1
        if record["status"] == "pass":
            bucket["passed"] += 1
    return summary


def _report_path(now: datetime) -> Path:
    # Unique per run -- a prior run's report (including the historical
    # 2026-09-04 one, generated by prompt v1) is never overwritten.
    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    return REPORTS_DIR / f"sales-turn-analysis-eval-{stamp}.json"


def run(*, dry_run: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixtures = _load_and_validate_fixtures()
    live = None if dry_run else _build_live_provider()
    mode = "live" if live else "dry_run"
    provider, model = live if live else (None, None)

    records: list[dict[str, Any]] = []
    for fixture in fixtures:
        prompt = sales_turn_analysis_prompt(
            profile_context=fixture["profile_context"],
            conversation_context=fixture["conversation_context"],
            customer_message=fixture["customer_message"],
        )
        record: dict[str, Any] = {"id": fixture["id"], "category": fixture["category"], "mode": mode}

        if provider is None:
            record["status"] = "skipped_dry_run"
            record["note"] = (
                "dry-run: fixtures.json schema, enum values, and prompt construction were validated "
                "locally; no Anthropic call was made and Anthropic output quality was NOT assessed"
            )
            records.append(record)
            continue

        request = AIRequest(
            prompt.identifier, prompt.version, "sales_turn_analysis_eval",
            prompt.system, prompt.user, SalesTurnAnalysisOutput,
            user_prompt_cache_prefix=prompt.user_cache_prefix,
        )
        started = perf_counter()
        try:
            result = provider.generate(request)
        except AIProviderError as exc:
            record["status"] = "provider_error"
            record["error_category"] = exc.category
            record["error"] = str(exc)
            records.append(record)
            continue
        wall_ms = round((perf_counter() - started) * 1000)

        failures = _check(result.output, fixture["customer_message"], fixture.get("expected", {}))
        record.update({
            "status": "pass" if not failures else "fail",
            "failures": failures,
            "output": result.output.model_dump(mode="json"),
            "wall_latency_ms": wall_ms,
            "metadata": _plain(result.metadata.as_audit_dict(confidence=result.output.confidence)),
        })
        records.append(record)

    summary = summarize(records, fixture_count=len(fixtures), mode=mode, model=model)
    return summary, records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="never call a live provider")
    args = parser.parse_args(argv)

    try:
        summary, records = run(dry_run=args.dry_run)
    except FixtureValidationError as exc:
        print(f"Fixture validation failed: {exc}", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = _report_path(now)
    out_path.write_text(json.dumps({"summary": summary, "records": records}, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nFull report: {out_path.relative_to(ROOT)}")

    if summary["mode"] == "dry_run":
        return 0
    return 0 if summary["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
