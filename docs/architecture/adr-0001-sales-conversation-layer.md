# ADR-0001: Separate sales-conversation state from process commitments

**Status:** Accepted for the foundation phase  
**Date:** 2026-09-04

## Context

Flywheel already has a deterministic `ProcessState` machine for lead-to-cash commitments. It controls qualification, booking, quoting, follow-up, winning, payment, completion, loss, reactivation, and human review. Anthropic is currently used through a provider-neutral boundary to extract intent and phrase constrained messages.

A complete sales conversation needs additional progress markers such as discovery, presentation, objection handling, and commitment. These markers describe conversational progress, not a business commitment. Adding them to `ProcessState` would make conversational turns capable of widening the transition policy that protects bookings, quotes, prices, and human approval.

## Decision

Introduce a separate `SalesStage` state machine and a closed `SalesMove` vocabulary.

- `SalesStage` records where the conversation is in the sales method.
- `ProcessState` remains authoritative for business execution.
- `SalesPolicyEngine` selects one allowed `SalesMove` from validated state and evidence.
- AI may recommend moves but cannot authorize one.
- A move that needs a booking, quote, callback, message, or handoff must call an existing or explicitly added server-side capability. That capability revalidates tenant, state, consent, availability, and policy.
- `SalesStage` transitions do not imply a `ProcessState` transition.
- Every nontrivial extracted signal contains exact customer evidence and a source message identifier.

## Initial contracts

The initial enums live in `src/domain/sales.py`. They are deliberately closed and covered by transition tests. Changes require an ADR/spec update because persisted values and eval fixtures will depend on them.

The first policy implementation is intentionally small. It establishes precedence and safety invariants before Anthropic prompts or persistence are connected:

1. human review wins;
2. an unresolved objection wins over presentation or commitment;
3. missing discovery information triggers one discovery question;
4. a confirmed need permits relevant presentation;
5. an addressed objection must be checked explicitly;
6. booking or callback requires an explicit customer signal;
7. unsupported context hands off instead of inventing a move.

## Consequences

- The sales layer can evolve without weakening `ProcessEngine`.
- AI behavior becomes testable as structured analysis plus deterministic policy.
- Persistence must store both sales and process state and must never infer one from the other.
- UI must display the distinction clearly.
- More code and mappings are required, but the authority boundary remains auditable.

## Deferred decisions

- Database table layout and retention policy.
- Tenant-specific playbook overrides.
- Knowledge-card retrieval and ranking implementation.
- Voice calling; the MVP callback is a scheduled staff task.
- Fine-tuning, which is explicitly outside the MVP.

