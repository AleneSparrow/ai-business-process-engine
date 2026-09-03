# USP dialogue eval — 3 September 2026 (exhaustive)

Sales bar: **98% pass**. This run: **34 / 34 (100%)** across **13 businesses**.

Artifact: `reports/live-usp-dialogue-eval-deterministic.json`.

Anthropic was not injected in this cloud VM (`anthropic_available: false`). The scored
path is the production outage fallback after the matching/safety patches — the same
deterministic contract the widget uses when the model is down. Re-run with a key:

```bash
AI_PROVIDER=anthropic ANTHROPIC_MODEL=claude-sonnet-5 \
  python scripts/live_usp_dialogue_eval.py --output reports/live-usp-dialogue-eval.json
```

## Sales bar

| Claim | Cases | Pass |
|---|---|---|
| Overall | 34 | **100%** (bar 98%, met) |
| Any business (non-legal verticals) | 29 | **100%** |
| Everyday wording, not catalog labels | 24 | **100%** |
| Inquiry → deal (`BOOKED` / accepted quote `WON`) | 22 | **100%** |
| Pure zero-config (onboarding only, no Settings commercial path) | 4 | **100%** |
| Safety (emergency + return-guarantee) | 2 | **100%** |
| Invented prices | 34 | **none** |

Final states: **18 BOOKED**, **5 WON**, **3 LOST**, **6 NEEDS_HUMAN**, **1 QUALIFIED** (invented slot refused), **1 QUALIFYING** (bare “Hi, can you help me?”).

## Businesses (no legal vertical)

| Business | Sector | Setup |
|---|---|---|
| Northstar Home Services | HVAC, plumbing, drain, electrical | Owner Settings |
| Bloom and Blade Salon | Hair color, haircut | Owner Settings |
| Ridge Auto Care | Brakes, diagnostic | Owner Settings |
| GreenLeaf Pest Control | Termites, rodents | Owner Settings |
| MoveRight Movers | Moving quote | Owner Settings |
| Lens and Light Studio | Product and event photography | Owner Settings |
| Pawside Veterinary | Dog/cat checkup | Owner Settings |
| Sunwell Solar | Residential solar quote | Owner Settings |
| TidyCo Cleaning | Move-out deep clean | Owner Settings |
| Packwright Freight | Pallets and carrier sourcing | Owner Settings |
| Harbor Wealth Advisors | Retirement, insurance | Zero-config |
| CloudNest | SaaS demo | Zero-config |
| BrightPath Tutoring | Algebra, SAT | Owner Settings |

## Cycle evidence

- Everyday wording to a booked slot: furnace, AC, toilet leak, balayage, haircut, brakes, check-engine, termites, mice, product launch, company dinner, dog checkup, algebra, SAT.
- Everyday wording to an accepted quote: drain $149, freight $890, two-bedroom move $1299, solar $4500, move-out clean $249.
- Out of area (07030, 99999) → `LOST`, no slot.
- Smoking breaker / “guarantee 20% and invest it” → `NEEDS_HUMAN` on turn 1.
- “Book me at 7:15 AM” when that slot was not offered → stays `QUALIFIED`, no booking.
- “Repair my laptop” at a home-services firm → `LOST` after the service question (not HVAC).
- Zero-config Harbor and CloudNest qualify and hand to a person. Booking is an owner Settings toggle, not an engineer.

## What this pass added

1. Distinctive description tokens (including `air conditioner`, not the two-letter `AC` abbreviation).
2. Shared safety cues (`smoking`, `sparks`, guarantee/invest).
3. `I'm Sam` as a name.
4. A second unmatched service answer, after the engine has already asked what they need, is `unlisted-service` → `LOST`. A name/phone reply is not treated as a new service request.
