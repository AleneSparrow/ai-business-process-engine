# Flywheel Demand — architecture

Product 2 is a separate bounded context. It compiles Marketing DNA, runs two state machines, and hands an inbound inquiry to the Business Process Engine at `NEW_LEAD`. It does not qualify, book, quote, follow up on a deal, or collect payment.

## Runtime model

A tenant owns one or more `Campaign` aggregates. A campaign owns frozen Marketing DNA, an append-only event history, and a setup state. Each attracted person is a `Prospect` aggregate: identity, score, consent ledger, sequence cursor, and journey state.

Both aggregates follow the same loop as the process engine:

`Trigger → Context → Decision → Action → Result → Next trigger`

Decisions in this milestone are `RULE`. AI may later draft wording inside an already approved brief; it cannot change state, claims, audience, or consent.

## Marketing DNA

Marketing DNA is tenant configuration for attraction, parallel to Business DNA for operations. The compiler (`build_marketing_dna`) reads Business DNA plus optional `MarketingOnboardingInput`. It never inspects an industry enum.

Required facts come from the catalog and service area. Optional owner input adds jobs, alternatives, substantiated proof, a physical postal address, and motion flags (attract and/or loyalty). At least one motion must stay on.

The JSON Schema is `config/marketing_dna.schema.json`. Secrets do not belong here. Delivery credentials stay in a future secrets manager, same rule as Business DNA integrations.

## Strategy funnel (tenant)

`StrategyService.compile` walks:

`MARKET_ANALYSIS → SEGMENTS_READY → POSITIONED → MOTION_SELECTED → ASSETS_READY`

`approve_live` is the only path to `LIVE`. Loyalty cannot go live without a physical postal address. Attract cannot go live without a content plan. `NEEDS_HUMAN` has no static exit; resume requires the recorded pending target.

## Prospect funnel (audience)

Skip-ahead is explicit in `PROSPECT_TRANSITIONS`. A first-touch inquiry is valid. The process-engine boundary is not:

`INQUIRED → HANDED_OFF`

`HANDED_OFF` is terminal inside Demand. `SUPPRESSED` returns only through a new `OPT_IN_RECORDED`. Duplicate event IDs are ignored.

Scoring thresholds live in Marketing DNA (`aware_min`, `engaged_min`, `intent_min`). Event types still win when they carry a stronger meaning: an inquiry is always an inquiry.

## Consent and claims

Loyalty sends are not cold outreach. `ConsentRecord` is append-only. The latest `GRANT`/`REVOKE` per channel is authoritative. SMS `GRANT` requires `evidence_id`.

`consent_gate` refuses a send without active consent, without a destination address, without a CAN-SPAM postal address and unsubscribe line on email, or without `STOP` language on SMS.

`claim_guard` refuses superlatives unless they sit inside an approved, substantiated claim. Owner proof without evidence is stored as `blocked` and cannot be referenced by a brief or sequence step.

## Handoff

`InquiryHandoff.to_intake_payload()` is the contract. Flywheel accepts that JSON at `POST /api/v1/businesses/{business_id}/demand/inquiries` (internal secret, Demand add-on must be active) and maps it to an ordinary `IncomingMessage`. Qualification and commercial work stay inside Flywheel. Demand never imports the process engine.

## Package boundary

`src/demand` does not import Flywheel. Flywheel does not import Demand. The only coupling is the JSON handoff contract and the Flywheel Billing add-on that grants `has_demand_access`.
