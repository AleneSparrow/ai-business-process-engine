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
```

## Run the tests

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest
```

## Next milestone

Add persistence behind repository interfaces, load and validate tenant Business DNA and workflow definitions at runtime, and introduce an action-executor boundary with an outbox. That creates a safe base for APIs, tenant isolation, real integrations, and an LLM provider in later milestones.
