# Sales turn analysis evals (proposal)

**Status:** proposed eval area, not yet agreed with the owner as the permanent
location (Part C of
`docs/agent-prompts/claude-code-sales-knowledge-and-evals.md` calls for
fixtures "in the eval/test area agreed with the owner" -- no such area existed
yet, so this is a starting proposal to accept, move, or replace).

## What this tests

`fixtures.json` exercises only the experimental prompt/schema pair:

- `src/ai/sales_prompts.py::sales_turn_analysis_prompt`
- `src/ai/sales_models.py::SalesTurnAnalysisOutput`

against the configured Anthropic model. It does **not** touch
`SalesPolicyEngine`, `ProcessState`, persistence, or the API -- those are out
of this task's scope and unaffected by anything here.

## Running

```bash
docker compose run --rm app python scripts/sales_turn_analysis_eval.py
```

Requires `AI_PROVIDER=anthropic` plus `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` to
already be configured in the environment (normally via `.env`, which Compose
passes through -- this script never reads or prints the key itself). Without
those, the script runs in dry-run mode.

**What dry-run actually checks, honestly:** it loads and validates
`fixtures.json` against a strict local schema (required keys, unique ids,
every `expected.*` enum value checked against the real domain enums, no
unknown `expected` keys) and constructs the prompt for every fixture. It does
**not** call Anthropic and says nothing whatsoever about output quality --
"dry-run passed" means the fixtures file and the prompt-building code are
sound, not that the model would answer any of them correctly. A malformed
fixtures file makes `--dry-run` exit non-zero (exit code 2); a well-formed one
exits 0 regardless of how many fixtures exist, since none of them were
scored.

Each run writes its own uniquely-named, timestamped report to `reports/`
(`sales-turn-analysis-eval-<UTC timestamp>.json`) -- it never overwrites a
prior run's report, including the historical `2026-09-04` one (generated
against an earlier prompt version, kept as-is). A live run's process exit
code is non-zero whenever the run did not fully succeed (see "Interpreting
results" below).

## Interpreting results

The summary distinguishes four fixture outcomes and never lets one silently
count as another:

- `passed` -- scored and every assertion in its `expected` block held.
- `assertion_failed` -- scored, but at least one assertion did not hold.
- `provider_errors` -- the model's response never became a scorable output at
  all (invalid structured output, timeout, rate limit, etc.) -- **not**
  counted toward `passed`, and not silently excluded from the denominator
  either.
- `skipped` -- dry-run only; never scored, never counted in `completed_count`.

`completed_count = passed + assertion_failed + provider_errors`.
`success_rate = passed / completed_count` (`null` when nothing completed, as
in a dry run). `assertion_pass_rate = passed / (passed + assertion_failed)`
is a secondary metric that, unlike `success_rate`, ignores provider errors --
useful for judging prompt content quality in isolation from tool-call-shape
reliability, but `successful` never uses it. The single `successful` boolean
is true only when `provider_errors == 0`, `assertion_failed == 0`, and
`completed_count == fixture_count` -- a run where 15/24 fixtures passed and 9
hit a provider error is reported as `success_rate: 0.625`, `successful:
false`, never as 100%.

## Fixture shape

Each entry in `fixtures.json` has an `id`, `category`, the inputs the prompt
needs (`profile_context`, `conversation_context`, `customer_message`), and an
`expected` block. `expected` keys are intentionally loose (`*_in` lists,
`forbidden_moves`, `min_confidence`, optional `note` for judgment calls the
script does not attempt to automate) rather than one exact expected object,
because `recommended_moves` are advisory and multiple stages/moves can be a
correct read of the same message -- see `SalesPolicyEngine`'s own precedence
rules in `src/engine/sales_policy.py` for what ultimately decides the move.

## Deliberately excluded categories

Per `docs/sales-agent-implementation-plan-ru.md` section 15's eval list, this
suite does not attempt: webhook/message replay, races against stale state,
human-takeover *enforcement*, or STOP-suppression *enforcement*. Those are
server/persistence behaviors a single-turn language classifier cannot be
meaningfully evaluated on in isolation. `stop-consent-001` is included because
recognizing STOP-adjacent *language* is a legitimate classifier behavior; the
suppression itself is enforced elsewhere and already covered by
`tests/test_sms_suppression.py`.
