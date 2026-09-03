# USP dialogue eval — 3 September 2026

Live multi-turn run across six businesses and four sectors. The matrix is
`scripts/live_usp_dialogue_eval.py`. This VM did not have `ANTHROPIC_API_KEY`
injected, so the scored run used the production **outage fallback**
(`DeterministicIntentExtractor`) after the matching/safety patches below.
The same script is what to run with Anthropic:

```bash
AI_PROVIDER=anthropic ANTHROPIC_MODEL=claude-sonnet-5 \
  python scripts/live_usp_dialogue_eval.py --output reports/live-usp-dialogue-eval.json
```

## Businesses

| Business | Sector | Setup | Commercial path |
|---|---|---|---|
| Northstar Home Services | Local home (HVAC, plumbing, drain, electrical) | Owner Settings after onboarding | Booking / quote / human review |
| Bloom and Blade Salon | Beauty | Owner Settings | Booking |
| Ridge Auto Care | Auto repair | Owner Settings | Booking |
| Harbor Wealth Advisors | Financial planning | Pure zero-config | Human review |
| BrightPath Tutoring | Education, remote | Owner Settings | Booking |
| Packwright Freight | B2B logistics | Owner Settings | Fixed quote |

No legal-vertical business. Everyday customer wording, not catalog labels.

## Results after the fallback patch

Artifact: `reports/live-usp-dialogue-eval-deterministic.json`.

| Metric | Before patch | After patch |
|---|---|---|
| Pass rate | 0 / 14 (0%) | **13 / 14 (92.9%)** |
| Service match | 21% (only the “any service is fine” cases) | **100%** |
| `to_deal` scenarios (booking or accepted quote) | 0% | **7 / 7 (100%)** |
| Safety (emergency + return-guarantee) | 0% | **2 / 2** |
| Zero-config Harbor retirement | fail, stuck QUALIFYING | **QUALIFIED → NEEDS_HUMAN** (the zero-config ceiling) |
| Invented prices | none | none |

Closed cycles observed on this run:

- HVAC, plumbing, salon color, brakes, remote tutoring → `BOOKED`
- Drain cleaning $149 and freight $890 → quote accepted → `WON`
- Out of area 07030 → `LOST` with the area message, not a fake slot
- Breaker panel smoking/sparks → `NEEDS_HUMAN` on turn 1
- “Guarantee me 20% and invest it” → `NEEDS_HUMAN` on turn 1

Example, Northstar furnace (everyday wording, no catalog name):

1. Customer: rattling furnace, name/ZIP/phone in one message.
2. Assistant asks only the configured HVAC question.
3. Customer: “The unit still runs.”
4. Three slots offered; “The second option works” → `BOOKED`.

## What was broken

1. **Zero-config wording died when Anthropic was down.** Fallback only matched the
   literal service name / `intake_keywords`. “My furnace is rattling” never
   became Heating & AC repair, so every vertical sat in `QUALIFYING`. That is
   exactly the outage path `src/ai/fallback.py` uses in production.
2. **Safety cues were AI-only.** `smoking` / `sparks` / `guarantee` / `invest it`
   lived in the Anthropic calibrator. The fallback only looked for the words
   `emergency`, `urgent`, `asap`. A smoking breaker panel stayed in the sales
   cycle.
3. **`I'm Sam at 10002` was not a name.** Only `My name is …` counted.

## Fixes in this change

- Distinctive-token match against the owner-supplied **service description**.
  Shared words (`repair`) do not pick a service on a multi-service catalog.
- Shared `src/domain/risk_cues.py` used by both the AI calibrator and the
  fallback extractor. `smoking` / `sparks` added.
- `I'm Sam` / `I am Riley` accepted when the given name is capitalized.

## Remaining gap

`Can you repair my laptop?` stays `QUALIFYING` (asks what service they need)
instead of `LOST` / `NEEDS_HUMAN`. The fallback will not invent
`unsupported_service` without a model. Live Anthropic should close this; it
is the one case to re-check on a keyed run.

Zero-config still does not auto-book: Harbor correctly qualifies and hands
to a person. Booking/quote require the owner Settings toggle, which is the
product rule, not an eval miss.
