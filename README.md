# AI Business Process Engine

AI Business Process Engine is the foundation of a configurable, production-oriented SaaS product for automating customer-facing processes at small and medium-sized businesses. It captures the reusable shape of lead-to-cash—qualification, booking or quoting, follow-up, payment, service, reviews, and reactivation—while each tenant supplies its own rules through **Business DNA**.

This is not a chatbot. Language understanding may eventually help with selected decisions, but process state, permissions, side effects, escalation, and audit history remain explicit and deterministic. AI proposes decisions through a controlled interface; it does not bypass workflow or risk controls.

## What this foundation contains

The MVP provides:

- typed domain models for leads, cases, events, decisions, actions, and results;
- an explicit state machine with terminal, escalation, and recovery paths;
- an event-driven process engine with idempotency and a complete in-memory audit trail;
- a decision router for rule, AI-placeholder, and human decisions;
- a reusable Lead-to-Cash workflow definition;
- a generic, validated Business DNA example and JSON Schema;
- executable Lead Intake and Qualification driven by Business DNA;
- provider-neutral intent extraction and customer-question generation boundaries;
- tests for transitions, rejection, audit history, escalation, idempotency, and end-to-end progression.

No database, API, UI, authentication, third-party integration, payment processing, or real LLM call is included yet.

## Architecture

Each step follows:

`Trigger -> Context -> Decision -> Action -> Result -> Next trigger`

`ProcessEngine` coordinates the step. `StateMachine` owns allowed transitions. `DecisionRouter` separates deterministic rules, future AI judgment, and human approval. Every received trigger and resulting decision/state change is appended to the case history. See [the architecture guide](docs/architecture.md) and [product specification](docs/product-spec.md).

## Repository structure

```text
config/       Business DNA example and schema
docs/         Product and architecture documentation
src/domain/   Domain types and state-transition rules
src/engine/   Decision routing and process orchestration
tests/        Executable behavior specifications
workflows/    Reusable workflow definitions
examples/     Local executable workflow demonstrations
```

## Run the tests

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest
```

## Lead Intake and Qualification

Milestone 2 executes the first real workflow:

`Incoming message -> Lead/case lookup -> Intent extraction -> Missing-information detection -> Qualification -> State transition -> Customer response`

The intake service scopes message idempotency by business, channel, and external message ID. Existing cases can be continued using an explicit case ID or a normalized phone/email match. Business DNA defines service aliases, required fields and their prompts, service areas, service-specific questions, confidence thresholds, booking eligibility, and escalation policy. No message is sent; the service returns a structured `CustomerResponse` for a future delivery adapter.

Run the local demonstration:

```bash
python examples/lead_qualification_demo.py
```

## Next milestone

Add persistence behind repository interfaces and make case updates, audit events, and idempotency claims atomic. Then introduce an action-executor boundary with an outbox. That creates a safe base for APIs, tenant isolation, real integrations, and an LLM provider in later milestones.
