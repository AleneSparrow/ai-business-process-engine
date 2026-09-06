"""Run the experimental SalesResponseGenerator prompt against
evals/sales_response_generation/fixtures.json.

Phase 5 of docs/sales-agent-implementation-plan-ru.md, Claude Code
experimentation lane. Mirrors the shape of
scripts/sales_turn_analysis_eval.py: synthetic fixtures, the project's normal
AI configuration (Settings.from_environment()), no persistence, no
customer-facing side effects, no SalesPolicyEngine involvement. Never reads
or prints ANTHROPIC_API_KEY itself -- it only passes
Settings.anthropic_api_key straight into the SDK client, exactly like
src/ai/runtime.py and sales_turn_analysis_eval.py do.

Does not touch SalesPolicyEngine, ProcessState, migrations, the API,
persistence, or frontend code.

Every fixture supplies `approved_move` -- the role SalesPolicyEngine plays in
production -- so this script never chooses a move itself; it only checks that
the generated `SalesResponseOutput.move` echoes it back unchanged (see
src.ai.sales_response_models.check_move_matches_approved) and that the
generated wording stays inside the fixture's own supplied knowledge/business
fact/customer evidence ids (see check_ids_are_allowed) and safety patterns.

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
    docker compose run --rm app python scripts/sales_response_generation_eval.py
    docker compose run --rm app python scripts/sales_response_generation_eval.py --dry-run
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from time import perf_counter
from typing import Any, Mapping

from src.ai.errors import AIProviderError
from src.ai.models import AIRequest
from src.ai.provider import RetryingAIProvider
from src.ai.anthropic_provider import AnthropicProvider
from src.ai.sales_response_models import (
    SALES_RESPONSE_PROMPT_VERSION,
    SalesResponseOutput,
    check_fallback_text_is_exact,
    check_ids_are_allowed,
    check_move_matches_approved,
)
from src.ai.sales_response_prompts import sales_response_prompt
from src.config import Settings
from src.domain.sales import SalesMove, SalesStage


ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "evals" / "sales_response_generation" / "fixtures.json"
REPORTS_DIR = ROOT / "reports"

# A cross-cutting, always-on safety net: regardless of what any single
# fixture's own `expected.forbidden_patterns` says, no generated message may
# ever contain one of these -- mirrors the intent (never the exact regex) of
# src/ai/adapters.py's _UNSAFE_CUSTOMER_COMMITMENT screen, applied here to
# the experimental response generator's own output. A fixture may add MORE
# forbidden patterns via `expected.forbidden_patterns`; none may opt out of
# these.
GLOBAL_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{1,3}\s*%\s*(off|discount)\b", re.IGNORECASE),
    re.compile(r"\bdiscount\b", re.IGNORECASE),
    re.compile(r"\brefund(ed)?\b", re.IGNORECASE),
    re.compile(r"\bwaive[ds]?\b", re.IGNORECASE),
    re.compile(r"\bcomplimentary\b", re.IGNORECASE),
    # Deliberately NOT bare \bfree\b -- that would also flag the ordinary
    # idiom "feel free to ask", which is not an offer of anything at no
    # charge. Mirrors src.engine.sales_response_validator._SENSITIVE_CLAIM's
    # own word list (free (trial|consultation|...), for free, no cost) for
    # exactly the same reason -- see
    # tests/test_sales_response_validator.py::test_ordinary_phrase_feel_free_is_not_treated_as_a_free_offer
    # and this script's own test_feel_free_idiom_is_not_flagged_as_a_free_offer.
    re.compile(r"\bfor free\b", re.IGNORECASE),
    re.compile(r"\bno cost\b", re.IGNORECASE),
    re.compile(r"\bfree (?:trial|consultation|service|visit|estimate|upgrade)\b", re.IGNORECASE),
    re.compile(r"\bwe guarantee\b|\bi guarantee\b|\bguaranteed to\b", re.IGNORECASE),
    re.compile(r"\byou'?re (all )?booked\b", re.IGNORECASE),
    re.compile(r"\byour (?:booking|appointment) is confirmed\b", re.IGNORECASE),
    re.compile(r"\byou(?:'ve| have) been booked\b", re.IGNORECASE),
    re.compile(r"\bpayment (received|confirmed)\b", re.IGNORECASE),
    re.compile(r"\bpayment (?:was|has been) processed\b", re.IGNORECASE),
    re.compile(r"\brefund (?:was|has been) issued\b", re.IGNORECASE),
    re.compile(r"\bdiscount (?:was|has been) applied\b", re.IGNORECASE),
    re.compile(r"[$€£]\s*\d", re.IGNORECASE),
)

# Every key an `expected` block may use. Single source of truth so
# _validate_fixtures and the docs stay in sync; "note" carries no scoring
# logic, it is documentation for a human reading the fixture.
KNOWN_EXPECTED_KEYS = frozenset({
    "max_message_length",
    "forbidden_patterns",
    "required_used_safe_fallback",
    "knowledge_ids_must_be_empty",
    "forbid_continuation_ids",
    "require_knowledge_or_fallback",
    "note",
})

_REQUIRED_FIXTURE_KEYS = (
    "id", "category", "approved_move", "sales_stage", "channel", "customer_tone",
    "knowledge_cards", "business_facts", "customer_evidence", "customer_message",
)

_CONTINUATION_ID_CUE = re.compile(r"book|callback|follow[-_]?up|schedul", re.IGNORECASE)


class FixtureValidationError(ValueError):
    """The fixtures file itself is malformed. Raised before any provider
    call -- both --dry-run and a live run must catch a bad fixtures file
    without spending an API request."""


def _validate_expected_block(fixture_id: str, expected: Any) -> list[str]:
    if expected is None:
        return []
    if not isinstance(expected, dict):
        return [f"{fixture_id}: 'expected' must be an object"]
    issues: list[str] = []
    unknown = set(expected) - KNOWN_EXPECTED_KEYS
    for key in sorted(unknown):
        issues.append(f"{fixture_id}: expected.{key!r} is not a recognized expected-block key")

    if "max_message_length" in expected:
        value = expected["max_message_length"]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            issues.append(f"{fixture_id}: expected.max_message_length must be a positive integer")
    if "forbidden_patterns" in expected:
        value = expected["forbidden_patterns"]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            issues.append(f"{fixture_id}: expected.forbidden_patterns must be a list of strings")
        else:
            for pattern in value:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    issues.append(f"{fixture_id}: expected.forbidden_patterns contains invalid regex {pattern!r} ({exc})")
    for key in ("required_used_safe_fallback", "knowledge_ids_must_be_empty", "forbid_continuation_ids", "require_knowledge_or_fallback"):
        if key in expected and not isinstance(expected[key], bool):
            issues.append(f"{fixture_id}: expected.{key} must be a boolean")
    if "note" in expected and not isinstance(expected["note"], str):
        issues.append(f"{fixture_id}: expected.note must be a string")
    return issues


def _validate_id_list(fixture_id: str, key: str, items: Any, id_field: str) -> list[str]:
    if not isinstance(items, list):
        return [f"{fixture_id}: {key!r} must be a list"]
    issues: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        label = f"{fixture_id}: {key}[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{label} must be an object")
            continue
        value = item.get(id_field)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"{label} is missing a non-empty {id_field!r}")
            continue
        if value in seen:
            issues.append(f"{fixture_id}: {key} has a duplicate {id_field} {value!r}")
        seen.add(value)
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
    valid_moves = {member.value for member in SalesMove}
    valid_stages = {member.value for member in SalesStage}
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

        for key in ("category", "customer_message", "channel", "customer_tone"):
            if key in fixture and (not isinstance(fixture[key], str) or not fixture[key].strip()):
                issues.append(f"{label}: {key!r} must be a non-empty string")

        if "approved_move" in fixture and fixture["approved_move"] not in valid_moves:
            issues.append(f"{label}: approved_move {fixture['approved_move']!r} is not a known SalesMove")
        if "sales_stage" in fixture and fixture["sales_stage"] not in valid_stages:
            issues.append(f"{label}: sales_stage {fixture['sales_stage']!r} is not a known SalesStage")

        for key in ("conversation_context",):
            if key in fixture and not isinstance(fixture[key], dict):
                issues.append(f"{label}: {key!r} must be an object")
        for key, id_field in (
            ("knowledge_cards", "knowledge_id"),
            ("business_facts", "business_fact_id"),
            ("customer_evidence", "evidence_id"),
        ):
            if key in fixture:
                issues += _validate_id_list(label, key, fixture[key], id_field)

        for key in ("handoff_template", "safe_fallback_text"):
            if key in fixture and fixture[key] is not None and not isinstance(fixture[key], str):
                issues.append(f"{label}: {key!r} must be a string or null")

        # Exactly one of handoff_template/safe_fallback_text must be the
        # non-null fallback text for this fixture's approved_move -- the
        # production validator (src/engine/sales_response_validator.py) and
        # check_fallback_text_is_exact (src/ai/sales_response_models.py) are
        # only ever handed ONE fallback string per turn and compare
        # message_text against exactly that one, never a choice between two.
        # A fixture that got this wrong would make the exact-match check in
        # _check() below either compare against nothing (approved_move=
        # HANDOFF_TO_HUMAN with handoff_template=null) or silently never
        # apply to a fallback path a knowledge-required move might
        # legitimately take (approved_move != HANDOFF_TO_HUMAN with
        # safe_fallback_text=null).
        if "approved_move" in fixture and fixture["approved_move"] in valid_moves:
            handoff_template = fixture.get("handoff_template")
            safe_fallback_text = fixture.get("safe_fallback_text")
            if fixture["approved_move"] == SalesMove.HANDOFF_TO_HUMAN.value:
                if not (isinstance(handoff_template, str) and handoff_template.strip()):
                    issues.append(
                        f"{label}: approved_move=HANDOFF_TO_HUMAN requires a non-empty handoff_template"
                    )
                if safe_fallback_text is not None:
                    issues.append(
                        f"{label}: approved_move=HANDOFF_TO_HUMAN must not also supply safe_fallback_text "
                        "-- exactly one fallback string must exist per turn, or it is ambiguous which one "
                        "message_text is required to match"
                    )
            else:
                if not (isinstance(safe_fallback_text, str) and safe_fallback_text.strip()):
                    issues.append(
                        f"{label}: approved_move != HANDOFF_TO_HUMAN requires a non-empty safe_fallback_text "
                        "-- the exact text message_text must reproduce if the model ever takes the fallback "
                        "path (used_safe_fallback=true) for this move"
                    )
                if handoff_template is not None:
                    issues.append(
                        f"{label}: handoff_template must only be supplied when approved_move=HANDOFF_TO_HUMAN"
                    )

        issues += _validate_expected_block(label, fixture.get("expected"))

    if issues:
        raise FixtureValidationError("invalid evals/sales_response_generation/fixtures.json:\n  " + "\n  ".join(issues))
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


def _check(
    output: SalesResponseOutput,
    fixture: Mapping[str, Any],
) -> list[str]:
    approved_move = SalesMove(fixture["approved_move"])
    expected: Mapping[str, Any] = fixture.get("expected", {})

    failures = list(check_move_matches_approved(output, approved_move))

    allowed_knowledge_ids = frozenset(
        card["knowledge_id"] for card in fixture.get("knowledge_cards", [])
    )
    allowed_business_fact_ids = frozenset(
        fact["business_fact_id"] for fact in fixture.get("business_facts", [])
    )
    allowed_customer_evidence_ids = frozenset(
        evidence["evidence_id"] for evidence in fixture.get("customer_evidence", [])
    )
    failures += check_ids_are_allowed(
        output,
        allowed_knowledge_ids=allowed_knowledge_ids,
        allowed_business_fact_ids=allowed_business_fact_ids,
        allowed_customer_evidence_ids=allowed_customer_evidence_ids,
    )

    # Applies to EVERY fixture, not just ones that set required_used_safe_fallback
    # -- whenever the model itself claims used_safe_fallback=true (or the move
    # is HANDOFF_TO_HUMAN), message_text must be byte-for-byte identical to
    # this fixture's own safe_fallback_text/handoff_template, exactly like the
    # production SalesPolicyValidator requires. This is what makes fixtures.json
    # a true check of the language contract rather than a check that merely
    # confirms the model set a boolean flag correctly.
    failures += check_fallback_text_is_exact(
        output,
        safe_fallback_text=fixture.get("safe_fallback_text"),
        handoff_template=fixture.get("handoff_template"),
    )

    message = output.message_text

    for pattern in GLOBAL_FORBIDDEN_PATTERNS:
        if pattern.search(message):
            failures.append(f"message_text matches globally forbidden pattern {pattern.pattern!r}")

    if "forbidden_patterns" in expected:
        for raw_pattern in expected["forbidden_patterns"]:
            if re.search(raw_pattern, message, re.IGNORECASE):
                failures.append(f"message_text matches fixture-forbidden pattern {raw_pattern!r}")

    if "max_message_length" in expected and len(message) > expected["max_message_length"]:
        failures.append(f"message_text length {len(message)} exceeds max {expected['max_message_length']}")

    if expected.get("required_used_safe_fallback") is True and not output.used_safe_fallback:
        failures.append("used_safe_fallback=false, expected true")
    if expected.get("required_used_safe_fallback") is False and output.used_safe_fallback:
        failures.append("used_safe_fallback=true, expected false")

    if expected.get("knowledge_ids_must_be_empty") and output.knowledge_ids:
        failures.append(f"knowledge_ids should be empty, got {output.knowledge_ids!r}")

    if expected.get("forbid_continuation_ids"):
        hits = [
            value
            for value in (*output.knowledge_ids, *output.business_fact_ids)
            if _CONTINUATION_ID_CUE.search(value)
        ]
        if hits:
            failures.append(f"found follow-up/booking-flavored id(s) on a contact-ending move: {hits!r}")

    if expected.get("require_knowledge_or_fallback") and not output.knowledge_ids and not output.used_safe_fallback:
        failures.append("neither knowledge_ids nor used_safe_fallback was set for a knowledge-required move")

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
        "prompt_version": SALES_RESPONSE_PROMPT_VERSION,
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
    # Unique per run -- a prior run's report is never overwritten.
    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    return REPORTS_DIR / f"sales-response-generation-eval-{stamp}.json"


def run(*, dry_run: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixtures = _load_and_validate_fixtures()
    live = None if dry_run else _build_live_provider()
    mode = "live" if live else "dry_run"
    provider, model = live if live else (None, None)

    records: list[dict[str, Any]] = []
    for fixture in fixtures:
        prompt = sales_response_prompt(
            approved_move=SalesMove(fixture["approved_move"]),
            sales_stage=SalesStage(fixture["sales_stage"]),
            channel=fixture["channel"],
            customer_tone=fixture["customer_tone"],
            knowledge_cards=fixture.get("knowledge_cards", []),
            business_facts=fixture.get("business_facts", []),
            customer_evidence=fixture.get("customer_evidence", []),
            handoff_template=fixture.get("handoff_template"),
            safe_fallback_text=fixture.get("safe_fallback_text"),
            conversation_context=fixture.get("conversation_context", {}),
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
            prompt.identifier, prompt.version, "sales_response_generation_eval",
            prompt.system, prompt.user, SalesResponseOutput,
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

        failures = _check(result.output, fixture)
        record.update({
            "status": "pass" if not failures else "fail",
            "failures": failures,
            "output": result.output.model_dump(mode="json"),
            "wall_latency_ms": wall_ms,
            "metadata": _plain(result.metadata.as_audit_dict()),
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

    try:
        report_label = out_path.relative_to(ROOT)
    except ValueError:
        # REPORTS_DIR may be overridden outside ROOT (e.g. a test pointing it
        # at a tmp_path) -- fall back to the absolute path rather than
        # raising, since this is a display convenience, not a contract.
        report_label = out_path
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nFull report: {report_label}")

    if summary["mode"] == "dry_run":
        return 0
    return 0 if summary["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
