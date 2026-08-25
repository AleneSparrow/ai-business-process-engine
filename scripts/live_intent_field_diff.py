"""Field-by-field IntentResult comparison: Sonnet-only intent vs. Haiku-4.5
intent, on the exact same 48 inputs (40 verticals + 8 safety challenges)
used by live_vertical_eval.py. Not an aggregate metric -- every field of
every case, with every disagreement listed explicitly. Also records wall
latency for both configurations.

Runs two full AI_PROVIDER=anthropic runtimes in-process (one per
ANTHROPIC_INTENT_MODEL) against the real API -- costs real tokens.
"""

from __future__ import annotations

import json
import runpy
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from src.ai.runtime import build_ai_runtime
from src.config import Settings
from src.domain.qualification import IncomingMessage

ROOT = Path(__file__).resolve().parents[1]

FIELDS = (
    "service_requested", "urgency", "requires_human", "unintelligible",
    "customer_tone", "customer_name", "phone", "email", "objection_phrase",
    "qualification_answers",
)


def _cases(matrix, build_dna):
    from importlib import import_module
    live_eval = import_module("scripts.live_vertical_eval")
    challenge_cases = live_eval._challenge_cases(matrix)

    cases = []
    for vertical in matrix:
        service = build_dna(vertical)["services"][0]
        cases.append({
            "label": f"normal:{vertical.industry}",
            "business_id": f"diff-{vertical.industry.replace(' ', '-').lower()}",
            "message": vertical.customer_message,
            "dna": build_dna(vertical),
            "expected_service": service["id"],
        })
    for index, (vertical, message, expectation) in enumerate(challenge_cases):
        cases.append({
            "label": f"challenge:{vertical.industry}:{expectation}",
            "business_id": f"diff-challenge-{index}-{vertical.industry.replace(' ', '-').lower()}",
            "message": message,
            "dna": build_dna(vertical),
            "expected_service": None,
        })
    return cases


def _field_value(intent: Any, field: str) -> Any:
    value = getattr(intent, field)
    if hasattr(value, "value"):  # Urgency / CustomerTone enums
        return value.value
    if isinstance(value, Mapping):  # qualification_answers is a mappingproxy, not a dict
        return dict(sorted(value.items()))
    return value


def _run_one(runtime, case: dict, index: int) -> dict:
    started = perf_counter()
    intent = runtime.intent_extractor.extract(
        IncomingMessage(
            business_id=case["business_id"],
            channel="webchat",
            external_message_id=f"diff-{index}",
            raw_text=case["message"],
            timestamp=datetime.now(timezone.utc),
        ),
        case["dna"],
    )
    wall_ms = round((perf_counter() - started) * 1000)
    row = {field: _field_value(intent, field) for field in FIELDS}
    row["wall_latency_ms"] = wall_ms
    row["reported_latency_ms"] = intent.ai_metadata.get("latency_ms")
    row["model"] = intent.ai_metadata.get("model")
    return row


def main() -> None:
    matrix_namespace = runpy.run_path(str(ROOT / "tests" / "test_vertical_sales_cycles.py"))
    matrix = tuple(matrix_namespace["VERTICALS"])
    build_dna = matrix_namespace["_dna"]
    cases = _cases(matrix, build_dna)

    base_settings = Settings.from_environment()
    import dataclasses
    sonnet_runtime = build_ai_runtime(dataclasses.replace(base_settings, anthropic_intent_model=None))
    haiku_runtime = build_ai_runtime(dataclasses.replace(base_settings, anthropic_intent_model="claude-haiku-4-5"))

    results = []
    for index, case in enumerate(cases):
        sonnet_row = _run_one(sonnet_runtime, case, index)
        haiku_row = _run_one(haiku_runtime, case, index)
        diffs = [
            field for field in FIELDS
            if sonnet_row[field] != haiku_row[field]
        ]
        results.append({
            "label": case["label"],
            "message": case["message"],
            "sonnet": sonnet_row,
            "haiku": haiku_row,
            "diff_fields": diffs,
        })
        print(f"[{index + 1}/{len(cases)}] {case['label']}: diffs={diffs or 'none'}", flush=True)

    sonnet_latencies = [r["sonnet"]["wall_latency_ms"] for r in results]
    haiku_latencies = [r["haiku"]["wall_latency_ms"] for r in results]

    def p95(values):
        ordered = sorted(values)
        return ordered[max(0, round(0.95 * len(ordered)) - 1)]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(results),
        "cases_with_any_diff": sum(1 for r in results if r["diff_fields"]),
        "diff_field_counts": {
            field: sum(1 for r in results if field in r["diff_fields"])
            for field in FIELDS
        },
        "sonnet_mean_latency_ms": round(mean(sonnet_latencies)),
        "sonnet_p95_latency_ms": p95(sonnet_latencies),
        "haiku_mean_latency_ms": round(mean(haiku_latencies)),
        "haiku_p95_latency_ms": p95(haiku_latencies),
    }

    # NOTE: write under scripts/, not reports/ -- only scripts/ (among
    # writable dirs) is bind-mounted in docker-compose.yml, so this survives
    # the --rm'd container; move it into reports/ afterward.
    output = ROOT / "scripts" / "live-intent-field-diff-2026-08-25.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nFull detail written to {output}")


if __name__ == "__main__":
    main()
