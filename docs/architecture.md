# Architecture

## Runtime model

The engine represents each customer journey as a `ProcessCase`, scoped by `business_id`. A case owns its lead, current state, timestamps, metadata, and append-only event history. The current implementation is deliberately in memory; these boundaries are intended to survive replacement by persistence and external adapters.

## Business DNA

Business DNA is tenant-owned configuration describing facts and policies: identity, catalog and pricing, service area and hours, qualification and scheduling constraints, sales and payment policy, communication style, AI permissions, escalation, and integration placeholders. The JSON Schema provides a versioned contract that is generic across industries. It must never contain API keys, passwords, tokens, or other secrets; integration entries reference separately secured connections.

## Processing cycle

1. **Event (trigger):** an immutable `ProcessEvent` announces something that happened and carries a unique idempotency ID.
2. **Context:** the engine reads the case state, tenant identity, lead details, event payload, and (in a later milestone) validated Business DNA.
3. **Decision:** `DecisionRouter` routes a `RULE`, `AI`, or `HUMAN` request. Rule decisions are deterministic. The AI provider is currently a deterministic placeholder. Human decisions explicitly pause automation.
4. **Action:** an `Action` describes a side effect separately from reasoning. This milestone models actions but does not execute integrations.
5. **Result:** `ActionResult` records whether an eventual executor succeeded and any returned data. A result can become the next trigger.
6. **State transition:** `StateMachine` is the sole authority on whether the chosen target is reachable from the current state.
7. **Audit trail:** the engine appends the incoming trigger, decision, and state change. It also appends rejected transitions and ignored duplicate deliveries.

This preserves the conceptual loop:

`Trigger -> Context -> Decision -> Action -> Result -> Next trigger`

## Decision and safety boundaries

`DecisionRouter` depends on an `AIDecisionProvider` protocol, so a real provider can be injected without changing orchestration. Provider output is untrusted: its decision type, target, approval, and confidence are checked before use. AI recommendations below the confidence threshold become human escalations. Explicitly high-risk actions and protected action types also escalate, even when presented as rules. Escalation stores one pending target; only a `HUMAN` decision with an identified approver can resume the case, and only to that target. A future authenticated boundary must establish that approver identity. Future action executors must independently enforce permissions and idempotency before side effects; a decision is not permission to bypass that boundary.

## Idempotency and failure semantics

Each case tracks processed trigger IDs independently from user metadata. Re-delivery appends `DUPLICATE_IGNORED` but neither re-decides nor changes state. Invalid transitions append `TRANSITION_REJECTED`, mark the trigger processed, and raise `InvalidTransition`, allowing an API or worker to report failure without silently corrupting state. Generated audit records carry the incoming trigger ID as their `causation_id`; event payloads and exposed history are immutable.

For production, processed IDs and audit events must be committed atomically with case state, and actions should use an outbox plus their own idempotency keys.

## Tenant isolation and persistence

`business_id` is mandatory on every case, establishing the tenant boundary. Future repositories and APIs must require it in every lookup and enforce isolation at both authorization and storage layers. Append-only audit storage, correlation IDs, actor identities, retention rules, and redaction policy should accompany persistence.

## Dependency direction

The domain package has no framework dependencies. The engine depends on domain abstractions. Future API, persistence, AI, and integration adapters should depend inward on these packages, keeping vendors and transport details outside core policy.
