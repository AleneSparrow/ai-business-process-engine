# Architecture

## Runtime model

The engine represents each customer journey as a `ProcessCase`, scoped by `business_id`. A case owns its lead, current state, timestamps, metadata, optimistic version, and append-only event history. Repository protocols isolate the domain and engine from SQLAlchemy; synchronous SQLAlchemy adapters persist the model to PostgreSQL-compatible SQL.

## Business DNA

Business DNA is tenant-owned configuration describing facts and policies: identity, catalog and pricing, service area and hours, qualification and scheduling constraints, sales and payment policy, communication style, AI permissions, escalation, and integration placeholders. The JSON Schema provides a versioned contract that is generic across industries. It must never contain API keys, passwords, tokens, or other secrets; integration entries reference separately secured connections.

## Processing cycle

1. **Event (trigger):** an immutable `ProcessEvent` announces something that happened and carries a unique idempotency ID.
2. **Context:** the engine reads the case state, tenant identity, lead details, event payload, and validated Business DNA supplied to the intake service.
3. **Decision:** `DecisionRouter` routes a `RULE`, `AI`, or `HUMAN` request. Rule decisions are deterministic. Provider-backed AI supplies validated understanding or wording but not state authority. Human decisions explicitly pause automation.
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

Persistent intake commits processed-message results, audit events, and case state atomically. Future side-effecting actions should use an outbox plus their own idempotency keys.

## Executable lead intake

`LeadIntakeService` accepts a validated `IncomingMessage`, checks its tenant and enabled channel, and claims an idempotency key scoped to `(business_id, channel, external_message_id)`. It resolves an active case by explicit case ID or normalized phone/email, records intake and extracted intent, merges new facts with prior lead context, and asks `QualificationService` for a structured outcome. State changes still pass through `ProcessEngine`; qualification code cannot mutate process state.

`IntentExtractor`, `QuestionGenerator`, and `CustomerResponseGenerator` are engine protocols. Their AI adapters depend on `StructuredAIProvider`; the first production adapter uses the official OpenAI SDK and typed Responses API parsing. Deterministic implementations remain available only when explicitly selected for tests, the offline demo, or local development. The returned `CustomerResponse` is a value object, not a sent message.

Prompts are centralized and versioned. Intent prompts contain only the raw customer message plus service IDs, names, aliases, and relevant qualification prompts. Wording prompts contain only the allowed missing items or approved outcome wording plus configured language, tone, and channel. Explicit phone/email fields, tenant and database IDs, pricing, integration configuration, and secrets are excluded. Customer content is delimited and declared untrusted; it cannot redefine Business DNA or grant discounts, refunds, payments, bookings, legal commitments, or policy exceptions.

Provider output is validated twice: Pydantic rejects a structurally invalid response, then the adapter verifies catalog aliases, unsupported-service evidence, qualification-answer IDs, the exact missing-item set, response type, and unsafe commitments. Invalid intent safely becomes a low-confidence human escalation. Wording validation failure and provider availability failure abort intake, allowing the database transaction and idempotency claim to roll back.

`LeadIntakeService` remains the lightweight in-memory implementation for fast domain tests and the local demo. `PersistentLeadIntakeService` executes the equivalent orchestration through a Unit of Work. Explicit case IDs are preferred for follow-up messages; phone/email matching is tenant-scoped, and conflicting identities are rejected rather than silently merging customers.

## Repository and transaction boundary

Repository protocols cover businesses, Business DNA, leads, cases, events, and idempotency records. SQLAlchemy implementations require `business_id` on every tenant-owned read or update. Composite tenant foreign keys ensure a process case can reference only a lead from the same business and an event can reference only a case from the same business.

Persistent intake is one database transaction:

1. load the tenant and active Business DNA;
2. claim the incoming message identity;
3. load or construct the tenant lead and case;
4. call the configured AI provider for understanding, then qualify deterministically;
5. execute state transitions through `ProcessEngine`;
6. save the lead/case and append new audit events;
7. attach the serialized logical result to the message claim;
8. commit everything together.

Any exception rolls back the entire Unit of Work. A stored message claim is never intentionally committed without its case and result.

## HTTP boundary

FastAPI owns transport validation and exposes `/health`, `/ready`, and versioned routes under `/api/v1`. `POST /api/v1/businesses/{business_id}/messages` constructs an `IncomingMessage` with the path tenant ID and delegates directly to `PersistentLeadIntakeService`; it does not introduce another idempotency layer. `GET /api/v1/businesses/{business_id}` returns safe business metadata without Business DNA or integration configuration.

Application startup requires `DATABASE_URL` and an explicit `AI_PROVIDER`, verifies database connectivity and AI configuration, creates one SQLAlchemy engine, and stores immutable dependency wiring on the FastAPI application. `AI_PROVIDER=openai` additionally requires `OPENAI_API_KEY` and `OPENAI_MODEL`; no paid provider call occurs during startup or readiness. Each repository operation still runs in a fresh Unit of Work whose session closes on success or failure. Alembic remains the only runtime schema authority.

Middleware accepts a constrained `X-Request-ID` or generates one, enforces a request-size ceiling when `Content-Length` is available, returns the correlation ID, and logs only safe routing metadata. Route logs include tenant ID and resulting state but never raw messages, contact details, credentials, or tokens. Validation and known domain conflicts use explicit public responses; unexpected errors return a correlation-bearing 500 without internal exception or database details.

The tenant path value is used for every repository lookup and for the domain `IncomingMessage`. An explicit case ID is queried together with that tenant ID, so another tenant's case is indistinguishable from a missing case. Authentication remains intentionally absent through Milestone 5 and must be added before exposing the service to untrusted clients.

## Database idempotency and concurrency

The `processed_messages` primary key is `(business_id, channel, external_message_id)`. A SHA-256 fingerprint covers normalized identity details and the original message content. On PostgreSQL, the repository first takes a transaction-scoped advisory lock derived from the full message identity. Contenders for the same identity therefore wait across processes until the current transaction commits, rolls back, or loses its connection. The database then uses `INSERT ... ON CONFLICT DO NOTHING RETURNING` to identify the claim owner while the composite primary key remains the authoritative uniqueness check. An identical fingerprint returns the completed stored result; a different fingerprint raises `IdempotencyCollisionError`. Because the lock is transaction-scoped and the claim is written in the intake transaction, failure releases the lock and rolls back an incomplete claim rather than permanently blocking retries. A committed claim without a result is treated as an invariant violation, not as normal in-progress processing.

Cases use optimistic concurrency. Each update includes the version that was loaded and atomically increments it. A zero-row update means another worker won; `StaleCaseError` aborts the losing transaction, so its state and candidate events never become visible. This protects distinct concurrent messages as well as direct competing transitions.

The advisory lock is acquired before any AI call. Concurrent identical HTTP messages therefore converge on one stored result and trigger one provider call where PostgreSQL coordination is available. A timeout or other exception releases the transaction-scoped lock and rolls back the claim, lead, case, and events together.

## AI failures and observability

The OpenAI client has an explicit configurable timeout and SDK retries disabled. A provider-neutral wrapper applies bounded exponential backoff only to typed timeout, rate-limit, network, and provider-internal failures. Invalid credentials, permissions, request/configuration errors, and invalid structured output are not retried. Public HTTP errors expose only stable application codes and correlation IDs, never provider response bodies or stack traces.

AI audit payloads contain provider, model, prompt ID/version, decision type, confidence, latency, success/failure category, attempt count, and input/output/total token counts when available. They exclude credentials, provider debug payloads, hidden reasoning, and duplicate customer-message text. Token metadata is observability for future cost accounting, not billing.

## Business DNA history

Business DNA uses `(business_id, version)` as its primary key. Adding a version locks the tenant business row, deactivates the prior version, allocates the next integer version, and activates the new record in one transaction. A partial unique index permits only one active version per tenant while retaining all prior versions.

## Migrations and configuration

`DATABASE_URL` and `AI_PROVIDER` are required and read from the environment. OpenAI mode additionally requires its API key and model; deterministic mode requires no provider credentials and is never an implicit fallback. Alembic owns production schema changes; the initial migration creates all tenant tables, composite constraints, partial unique indexes, and audit indexes. Docker Compose starts PostgreSQL and the API, waits for database health, and applies migrations before Uvicorn starts. Credentials in `.env.example` are local-development placeholders and no secrets are stored in Business DNA.

## Tenant isolation and persistence

`business_id` is mandatory on every case, repository method, and tenant API route, establishing the current storage boundary. Future authentication must authorize the caller for that tenant before repository access. Actor identities, retention rules, and redaction policy remain future audit-hardening work.

## Dependency direction

The domain package has no framework dependencies. The engine depends on domain abstractions. The persistence, API, and AI adapters depend inward on these packages. Engine protocols do not import the OpenAI SDK, keeping vendor and transport details outside core policy.
