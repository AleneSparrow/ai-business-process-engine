# Product specification

## Product

AI Business Process Engine is a multi-tenant SaaS foundation for reusable customer-facing workflows. It serves SMBs whose operational journeys share a common structure but differ in policy, language, service catalog, and integrations.

## Problem and approach

Businesses repeatedly implement the same coordination logic across inboxes, calendars, spreadsheets, and staff. The engine separates that reusable process logic from tenant-specific **Business DNA**. A business can configure identity, services, prices, geography, hours, customer-data requirements, qualification, booking, sales, payment, communications, AI permissions, escalation, and integration references without changing Python code.

Business DNA contains operational policy, not secrets. Integration entries hold opaque connection references; a future secrets manager owns credentials.

## MVP scope

The first workflow covers:

`New lead -> Contact -> Qualification -> Qualified -> Booking or Quote -> Follow-up -> Won -> Payment -> Completed -> Review request -> Reactivation`

At applicable points a case can become lost, cancelled, or require a human. Milestone 3 provides durable PostgreSQL-backed persistence while retaining lightweight in-memory implementations for unit tests and the local demo. Decisions remain deterministic, including a placeholder at the future AI boundary.

Milestone 2 makes the intake and qualification segment executable. Incoming channel messages create or reuse a tenant-scoped lead and case, produce deterministic intent, detect missing fields and service-specific answers, evaluate service and geographic fit, generate configured questions, and reach `QUALIFIED`, `LOST`, `QUALIFYING`, or `NEEDS_HUMAN`. Responses are returned as structured values and are not delivered externally.

Milestone 3 persists tenants, versioned Business DNA, leads, cases, audit events, and processed-message results through repository abstractions and PostgreSQL-compatible SQLAlchemy adapters. Persistent intake is atomic, message claims are protected by database uniqueness, tenant ownership is enforced in queries and composite foreign keys, and stale case writers are rejected with optimistic concurrency.

## Principles

- Business rules and state validity are deterministic.
- AI is advisory and permission-bound.
- Low-confidence decisions and high-risk actions require an identified human; escalation can resume only to its recorded pending target.
- Trigger IDs make processing idempotent within a case, while database message claims make intake idempotent across workers and restarts.
- Every accepted trigger, decision, state change, rejection, and duplicate is auditable.
- Tenant IDs are mandatory at the domain and repository boundaries, and persistence enforces tenant-qualified relationships.
- Reasoning and action execution are separate concerns.

## Not in this milestone

Persistence is implemented. Future milestones defer the HTTP API, authentication, external integrations, queues, production deployment, billing, real payment processing, user interfaces, and LLM calls.

## Acceptance criteria

- All required states and domain models exist with type hints.
- Invalid state changes fail explicitly and are recorded.
- AI risk or insufficient confidence escalates to `NEEDS_HUMAN`.
- Replayed event IDs do not repeat a state change.
- The Lead-to-Cash happy path and its quote branch pass automated tests.
