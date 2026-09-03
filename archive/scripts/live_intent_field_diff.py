"""Retired 2026-08-25. Field-by-field IntentResult comparison between
Sonnet-only intent extraction and a Haiku-4.5 per-role override, run once
against the real Anthropic API on the same 48 inputs (40 verticals + 8
safety challenges) used by live_vertical_eval.py.

Result: 15 of 48 cases disagreed on at least one field (3 service_requested,
2 urgency, 1 requires_human, 3 customer_tone, 12 qualification_answers),
including an intermittent false requires_human=True on an ordinary legal
intake message ("I need to speak with a lawyer about a custody agreement").
Full per-field detail: archive/reports/live-intent-field-diff-2026-08-25.json.

Alena decided against enabling Haiku on this basis -- see
claude/unit-economics-and-urgency-default.md section 5. The per-role model
override (ANTHROPIC_INTENT_MODEL / OPENAI_INTENT_MODEL, Settings, and the
branch in src/ai/runtime.py it drove) was removed from the codebase the same
day, so this script can no longer run as written -- kept as a pointer to the
report and the reasoning, not as live tooling.
"""
