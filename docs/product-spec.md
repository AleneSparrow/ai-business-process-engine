# Product specification

## Product

AI Business Process Engine is a multi-tenant SaaS foundation for reusable customer-facing workflows. It serves SMBs whose operational journeys share a common structure but differ in policy, language, service catalog, and integrations.

## Problem and approach

Businesses repeatedly implement the same coordination logic across inboxes, calendars, spreadsheets, and staff. The engine separates that reusable process logic from tenant-specific **Business DNA**. A business can configure identity, services, prices, geography, hours, customer-data requirements, qualification, booking, sales, payment, communications, AI permissions, escalation, and integration references without changing Python code.

Business DNA contains operational policy, not secrets. Integration entries hold opaque connection references; a future secrets manager owns credentials.

## MVP scope

The first workflow covers:

`New lead -> Contact -> Qualification -> Qualified -> Booking or Quote -> Follow-up -> Won -> Payment -> Completed -> Review request -> Reactivation`

At applicable points a case can become lost, cancelled, or require a human. The foundation currently runs in memory and uses deterministic decisions, including a deterministic placeholder at the future AI boundary.

## Principles

- Business rules and state validity are deterministic.
- AI is advisory and permission-bound.
- Low-confidence decisions and high-risk actions require an identified human; escalation can resume only to its recorded pending target.
- Trigger IDs make processing idempotent within a case.
- Every accepted trigger, decision, state change, rejection, and duplicate is auditable.
- Tenant IDs are present at the domain boundary; persistence must enforce tenant isolation later.
- Reasoning and action execution are separate concerns.

## Not in this milestone

Persistence, APIs, user interfaces, authentication, billing, real payment processing, CRM/calendar/messaging adapters, cloud infrastructure, and LLM calls are deliberately deferred.

## Acceptance criteria

- All required states and domain models exist with type hints.
- Invalid state changes fail explicitly and are recorded.
- AI risk or insufficient confidence escalates to `NEEDS_HUMAN`.
- Replayed event IDs do not repeat a state change.
- The Lead-to-Cash happy path and its quote branch pass automated tests.
