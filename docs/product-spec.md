# Product specification

## Product

AI Business Process Engine is a multi-tenant SaaS foundation for reusable customer-facing workflows. It serves SMBs whose operational journeys share a common structure but differ in policy, language, service catalog, and integrations.

## Problem and approach

Businesses repeatedly implement the same coordination logic across inboxes, calendars, spreadsheets, and staff. The engine separates that reusable process logic from tenant-specific **Business DNA**. A business can configure identity, services, prices, geography, hours, customer-data requirements, qualification, booking, sales, payment, communications, AI permissions, escalation, and integration references without changing Python code.

Business DNA contains operational policy, not secrets. Integration entries hold opaque connection references; a future secrets manager owns credentials.

## MVP scope

The first workflow covers:

`New lead -> Contact -> Qualification -> Qualified -> Booking or Quote -> Follow-up -> Won -> Payment -> Completed -> Review request -> Reactivation`

At applicable points a case can become lost, cancelled, or require a human. Milestone 3 provides durable PostgreSQL-backed persistence while retaining lightweight in-memory implementations for unit tests and the local demo. Business decisions remain deterministic even when Milestone 5 AI supplies understanding and customer-facing wording.

Milestone 2 makes the intake and qualification segment executable. Incoming channel messages create or reuse a tenant-scoped lead and case, produce deterministic intent, detect missing fields and service-specific answers, evaluate service and geographic fit, generate configured questions, and reach `QUALIFIED`, `LOST`, `QUALIFYING`, or `NEEDS_HUMAN`. Responses are returned as structured values and are not delivered externally.

Milestone 3 persists tenants, versioned Business DNA, leads, cases, audit events, and processed-message results through repository abstractions and PostgreSQL-compatible SQLAlchemy adapters. Persistent intake is atomic, message claims are protected by database uniqueness, tenant ownership is enforced in queries and composite foreign keys, and stale case writers are rejected with optimistic concurrency.

Milestone 4 exposes that persisted workflow through a versioned FastAPI service. The HTTP boundary validates incoming messages, resolves tenants from the path, preserves database idempotency and transaction semantics, returns structured qualification outcomes, propagates correlation IDs, and maps known failures to safe HTTP responses. Authentication is intentionally not part of this milestone.

Milestone 5 introduces an explicit provider-neutral structured AI boundary and an OpenAI implementation. AI extracts intent and qualification answers and drafts constrained clarification, unsupported-service, outside-area, and human-escalation wording. Pydantic schemas and adapter-level policy validation treat every output as untrusted. Deterministic rules still decide service fit, geography, qualification, booking permission, escalation, and state transitions.

## Principles

- Business rules and state validity are deterministic.
- AI is advisory and permission-bound.
- Low-confidence decisions and high-risk actions require an identified human; escalation can resume only to its recorded pending target.
- Trigger IDs make processing idempotent within a case, while database message claims make intake idempotent across workers and restarts.
- Every accepted trigger, decision, state change, rejection, and duplicate is auditable.
- Tenant IDs are mandatory at the domain and repository boundaries, and persistence enforces tenant-qualified relationships.
- Reasoning and action execution are separate concerns.

## Not in this milestone

Persistence, the lead-intake HTTP API, and provider-backed LLM understanding/wording are implemented. Future milestones defer authentication and authorization, outbound messaging and other external integrations, queues, production deployment, billing, real payment processing, and user interfaces.

## Acceptance criteria

- All required states and domain models exist with type hints.
- Invalid state changes fail explicitly and are recorded.
- AI risk or insufficient confidence escalates to `NEEDS_HUMAN`.
- Replayed event IDs do not repeat a state change.
- Tenant-scoped HTTP intake preserves replay, collision, escalation, and concurrency behavior.
- AI output is structured, policy-validated, privacy-minimized, auditable, and unable to override deterministic qualification.
- Provider failure rolls back intake, while low-confidence or invalid intent escalates safely.
- The Lead-to-Cash happy path and its quote branch pass automated tests.
