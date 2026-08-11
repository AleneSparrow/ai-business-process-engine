# Architecture

## Runtime model

The engine represents each customer journey as a `ProcessCase`, scoped by `business_id`. A case owns its lead, current state, timestamps, metadata, optimistic version, and append-only event history. Repository protocols isolate the domain and engine from SQLAlchemy; synchronous SQLAlchemy adapters persist the model to PostgreSQL-compatible SQL.

## Business DNA

Business DNA is tenant-owned configuration describing facts and policies: identity, catalog and pricing, service area and hours, qualification and scheduling constraints, sales and payment policy, communication style, AI permissions, escalation, and integration placeholders. The JSON Schema provides a versioned contract that is generic across industries. It must never contain API keys, passwords, tokens, or other secrets; integration entries reference separately secured connections.

## Processing cycle

1. **Event (trigger):** an immutable `ProcessEvent` announces something that happened and carries a unique idempotency ID.
2. **Context:** the engine reads the case state, tenant identity, lead details, event payload, and validated Business DNA supplied to the intake service.
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

## Executable lead intake

`LeadIntakeService` accepts a validated `IncomingMessage`, checks its tenant and enabled channel, and claims an idempotency key scoped to `(business_id, channel, external_message_id)`. It resolves an active case by explicit case ID or normalized phone/email, records intake and extracted intent, merges new facts with prior lead context, and asks `QualificationService` for a structured outcome. State changes still pass through `ProcessEngine`; qualification code cannot mutate process state.

`IntentExtractor` and `QuestionGenerator` are protocols. Their deterministic implementations support tests and local operation without network access. Questions come from Business DNA field prompts and service-specific qualification prompts. The returned `CustomerResponse` is a value object, not a sent message.

`LeadIntakeService` remains the lightweight in-memory implementation for fast domain tests and the local demo. `PersistentLeadIntakeService` executes the equivalent orchestration through a Unit of Work. Explicit case IDs are preferred for follow-up messages; phone/email matching is tenant-scoped, and conflicting identities are rejected rather than silently merging customers.

## Repository and transaction boundary

Repository protocols cover businesses, Business DNA, leads, cases, events, and idempotency records. SQLAlchemy implementations require `business_id` on every tenant-owned read or update. Composite tenant foreign keys ensure a process case can reference only a lead from the same business and an event can reference only a case from the same business.

Persistent intake is one database transaction:

1. load the tenant and active Business DNA;
2. claim the incoming message identity;
3. load or construct the tenant lead and case;
4. extract and qualify without external side effects;
5. execute state transitions through `ProcessEngine`;
6. save the lead/case and append new audit events;
7. attach the serialized logical result to the message claim;
8. commit everything together.

Any exception rolls back the entire Unit of Work. A stored message claim is never intentionally committed without its case and result.

## Database idempotency and concurrency

The `processed_messages` primary key is `(business_id, channel, external_message_id)`. A SHA-256 fingerprint covers normalized identity details and the original message content. On PostgreSQL, the repository first takes a transaction-scoped advisory lock derived from the full message identity. Contenders for the same identity therefore wait across processes until the current transaction commits, rolls back, or loses its connection. The database then uses `INSERT ... ON CONFLICT DO NOTHING RETURNING` to identify the claim owner while the composite primary key remains the authoritative uniqueness check. An identical fingerprint returns the completed stored result; a different fingerprint raises `IdempotencyCollisionError`. Because the lock is transaction-scoped and the claim is written in the intake transaction, failure releases the lock and rolls back an incomplete claim rather than permanently blocking retries. A committed claim without a result is treated as an invariant violation, not as normal in-progress processing.

Cases use optimistic concurrency. Each update includes the version that was loaded and atomically increments it. A zero-row update means another worker won; `StaleCaseError` aborts the losing transaction, so its state and candidate events never become visible. This protects distinct concurrent messages as well as direct competing transitions.

## Business DNA history

Business DNA uses `(business_id, version)` as its primary key. Adding a version locks the tenant business row, deactivates the prior version, allocates the next integer version, and activates the new record in one transaction. A partial unique index permits only one active version per tenant while retaining all prior versions.

## Migrations and configuration

`DATABASE_URL` is required and read from the environment. Alembic owns production schema changes; the initial migration creates all tenant tables, composite constraints, partial unique indexes, and audit indexes. The local Compose file starts PostgreSQL only and stores its data in a named volume. Credentials in `.env.example` are local-development placeholders and no secrets are stored in Business DNA.

## Tenant isolation and persistence

`business_id` is mandatory on every case and repository method, establishing the current storage boundary. Future APIs must still enforce authorization before calling these repositories. Correlation IDs, actor identities, retention rules, and redaction policy remain future audit-hardening work.

## Dependency direction

The domain package has no framework dependencies. The engine depends on domain abstractions. The persistence adapter and future API, AI, and integration adapters depend inward on these packages, keeping vendors and transport details outside core policy.
