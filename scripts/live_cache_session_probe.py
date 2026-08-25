"""Measure real Anthropic prompt-cache hit rate for two scenarios
(task-cost-reduction.md): several messages in one session (same business,
should hit the Business-DNA-level cache breakpoint from turn 2 onward) vs.
the first message of a fresh business after a pause (should miss it, same
as every business's first-ever message). Prints per-call
input/output/cache_read/cache_write tokens -- no aggregation, no guessing.

Temporary measurement script, not part of the permanent eval suite.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.ai.runtime import build_ai_runtime
from src.config import Settings
from src.domain.business_dna_builder import OnboardingInput, OnboardingService, build_business_dna
from src.domain.qualification import IncomingMessage

NOW = datetime.now(timezone.utc)


def _dna(business_id: str) -> dict:
    return build_business_dna(OnboardingInput(
        business_id=business_id,
        business_name="Cache Probe Roofing",
        industry="Roofing",
        tone="Friendly & direct",
        services=(
            OnboardingService("Roof repair", ("What is leaking?",), "Roof leak diagnosis and repair"),
            OnboardingService("Roof replacement", (), "Full roof replacement estimates"),
        ),
        service_zip_codes=(),
        enforce_service_area=False,
    ))


def _call(runtime, dna: dict, business_id: str, external_id: str, raw_text: str) -> dict:
    intent = runtime.intent_extractor.extract(
        IncomingMessage(
            business_id=business_id,
            channel="webchat",
            external_message_id=external_id,
            raw_text=raw_text,
            timestamp=NOW,
        ),
        dna,
    )
    meta = dict(intent.ai_metadata)
    return {
        "external_id": external_id,
        "raw_text": raw_text,
        "model": meta.get("model"),
        "input_tokens": meta.get("input_tokens"),
        "output_tokens": meta.get("output_tokens"),
        "cache_read_tokens": meta.get("cache_read_tokens"),
        "cache_write_tokens": meta.get("cache_write_tokens"),
    }


def main() -> None:
    runtime = build_ai_runtime(Settings.from_environment())
    results: dict[str, object] = {"model_name": runtime.model_name}

    # Scenario A: one session, three messages from the same lead to the same
    # business -- turn 1 cache-misses the Business-DNA block (first time this
    # exact business/DNA has been sent), turns 2-3 should hit it.
    session_business = f"cache-probe-session-{NOW.timestamp()}"
    dna = _dna(session_business)
    session_calls = [
        _call(runtime, dna, session_business, "s1", "My roof is leaking near the chimney"),
        _call(runtime, dna, session_business, "s2", "It's been leaking for about a week"),
        _call(runtime, dna, session_business, "s3", "My name is Alex, phone 555-201-3344"),
    ]
    results["session_same_business"] = session_calls

    # Scenario B: three DIFFERENT businesses, each sending its first-ever
    # message -- every one of these should miss the Business-DNA breakpoint
    # (never seen that exact DNA before), same as a real business's first
    # message after a pause.
    fresh_calls = []
    for index in range(3):
        business_id = f"cache-probe-fresh-{NOW.timestamp()}-{index}"
        fresh_dna = _dna(business_id)
        fresh_calls.append(_call(runtime, fresh_dna, business_id, f"f{index}", "My roof is leaking near the chimney"))
    results["fresh_business_each_time"] = fresh_calls

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
