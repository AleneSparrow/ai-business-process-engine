# Sales layer architecture audit

**Date:** 2026-09-04  
**Scope:** foundation audit before sales-agent persistence, Anthropic prompts, API, and UI

## Executive finding

The repository already has strong deterministic boundaries for qualification and commercial commitments. The new sales-agent work should extend them with a separate conversational sales layer rather than replace or widen them.

The safest integration point is between persisted conversation intake and the existing qualification/commercial orchestration:

```text
conversation message
  → existing intent extraction
  → new sales turn analysis
  → evidence-validated profile update
  → new deterministic sales policy
  → approved wording or existing commercial capability
  → existing ProcessEngine / outbox / audit
```

## Existing components to reuse

### Business authority

- `ProcessState` and `StateMachine` define lead-to-cash transitions.
- `ProcessEngine` and `DecisionRouter` guard state changes and human approval.
- `QualificationService` owns deterministic qualification outcomes.
- `CommercialWorkflowService` owns booking, quotes, payment-request preparation, and related guards.
- Business DNA owns tenant-specific services, rules, prices, booking constraints, communication policy, and AI permissions.

### AI boundary

- Prompts are centralized and versioned in `src/ai/prompts.py`.
- Provider output is structurally and semantically validated in the adapters.
- Anthropic and OpenAI share provider-neutral protocols.
- AI currently extracts intent, tone, objection evidence, and constrained wording.
- Deterministic fallbacks already exist for provider failure or invalid output.

### Conversation safety

- Conversation tokens are tenant-bound and persisted as hashes.
- Ordered messages, idempotency, and optimistic concurrency are present.
- Human takeover pauses autonomous turns.
- Terminal cases do not silently restart the ordinary flow.
- Context is bounded and contact information is redacted before model use.

### External effects

- Follow-up, CRM, and conversational SMS use durable delivery records/outbox behavior.
- SMS consent and STOP suppression already gate outbound messages.
- Booking capacity and slot validity are rechecked server-side.

## Gaps the sales layer must fill

- No separate persisted sales-conversation stage.
- No structured customer sales profile containing goal, problem, desired outcome, decision criteria, commitment, and objection lifecycle.
- No closed next-best-action policy spanning discovery, presentation, objections, commitment, callback, and nurture.
- Existing objection handling acknowledges or reassures but does not persist `active → diagnosed → addressed → resolved`.
- Follow-up cadence is durable but is not yet selected from a closed contextual reason vocabulary.
- No approved, versioned sales knowledge-card repository with provenance.
- No response provenance linking each claim to a knowledge card, Business DNA fact, or customer evidence.
- No sales-specific policy validator after message generation.
- No callback task capability; existing SMS support is not a voice agent.
- No shadow-mode comparison between the current response and a proposed sales-agent response.

## Decisions fixed for the foundation

1. `SalesStage` remains separate from `ProcessState`.
2. AI recommendations never authorize `SalesMove`.
3. Sales analysis and sales response generation are separate calls/contracts.
4. Nontrivial customer signals require exact evidence and a source message ID.
5. Missing approved knowledge causes safe handoff rather than improvisation.
6. An addressed objection is not resolved without a subsequent customer signal.
7. Existing booking, quote, human-review, tenant, consent, and outbox controls remain authoritative.
8. Fine-tuning is deferred until production evidence identifies a specific problem it can solve.

## Initial implementation seam

The first foundation modules are:

- `src/domain/sales.py`: closed enums and provider-neutral validated values;
- `src/engine/sales_policy.py`: stage transition policy and deterministic next move;
- `tests/test_sales_domain.py`: validation and evidence invariants;
- `tests/test_sales_policy.py`: policy precedence and safe behavior.

These modules intentionally have no database or Anthropic dependency. Persistence and provider adapters should depend on them, not the reverse.

## Persistence plan for the next backend phase

Prefer explicit tables over storing the full sales profile in `ProcessCase.metadata`:

- `sales_profiles`: one current profile per `(business_id, case_id)`, optimistic version;
- `sales_turns`: append-only analysis/decision/provenance record;
- `sales_objections`: objection lifecycle and evidence reference;
- `sales_playbook_versions`: immutable published version plus draft state;
- `sales_knowledge_cards`: immutable approved versions and candidate/rejected workflow;
- `sales_follow_up_plans`: scheduled contextual follow-up intent, separate from delivery attempts.

All foreign keys and repository lookups must include `business_id`. Publication of a playbook version and assignment to a business must be atomic. Raw source documents should not be copied into audit events.

## Documentation inconsistencies found and resolved

The audit found the following stale statements; the foundation change updates their source documents:

- `docs/architecture.md` says conflicting service, location, and preferred-time facts are retained and force human review. Current `LeadIntakeService._merge_intent` accepts explicit corrections for those facts while retaining identity conflict protection.
- `docs/product-spec.md` still describes some shared multi-worker controls and outbox work as future, although migrations and services now implement significant parts of that behavior.
- `CLAUDE.md` says the product works for any business without individual setup. The code supports cross-vertical configuration, but the sales knowledge/playbook feature does not yet exist and must not be marketed as completed.

The corrections describe current behavior without expanding product guarantees. They do not claim automatic legal compliance or universal zero-configuration sales behavior before the sales knowledge layer is complete.

## Required reviews before persistence work

- Product owner approves the final `SalesStage` and `SalesMove` vocabulary.
- Product owner decides whether `WON` in the sales layer means accepted next step, booked appointment, accepted quote, or the existing process `WON` event.
- Product owner defines minimum discovery fields for the zero-config playbook.
- Product owner chooses the first legally usable sales methodology sources.
- Backend review confirms retention/redaction rules for evidence excerpts.

## Foundation acceptance result

- Separate stage and move contracts: implemented.
- Closed transition map: implemented.
- Evidence-bound signal and objection values: implemented.
- Deterministic safety precedence: implemented.
- Persistence/API/Anthropic/UI wiring: intentionally deferred to subsequent phases.
