# AI Business Process Engine

AI Business Process Engine is the foundation of a configurable, production-oriented SaaS product for automating customer-facing processes at small and medium-sized businesses. It captures the reusable shape of lead-to-cash—qualification, booking or quoting, follow-up, payment, service, reviews, and reactivation—while each tenant supplies its own rules through **Business DNA**.

This is not a chatbot. Language understanding may eventually help with selected decisions, but process state, permissions, side effects, escalation, and audit history remain explicit and deterministic. AI proposes decisions through a controlled interface; it does not bypass workflow or risk controls.

## What this foundation contains

The MVP provides:

- typed domain models for leads, cases, events, decisions, actions, and results;
- an explicit state machine with terminal, escalation, and recovery paths;
- an event-driven process engine with idempotency and append-only audit history in memory or durable storage;
- a decision router for rule, AI-placeholder, and human decisions;
- a reusable Lead-to-Cash workflow definition;
- a generic, validated Business DNA example and JSON Schema;
- executable Lead Intake and Qualification driven by Business DNA;
- provider-neutral intent extraction and customer-question generation boundaries;
- SQLAlchemy repositories with tenant-scoped persistence and optimistic concurrency;
- database-backed, concurrency-safe incoming-message idempotency;
- versioned Business DNA and reproducible Alembic migrations;
- a versioned FastAPI boundary with validated tenant routes and safe error responses;
- tests for transitions, rejection, audit history, escalation, idempotency, and end-to-end progression.

Milestone 4 exposes the persisted intake workflow over HTTP with health/readiness checks, request correlation IDs, structured logging, OpenAPI documentation, and Docker Compose startup. Authentication, UI, third-party integrations, payment processing, and real LLM calls are not included yet.

## Architecture

Each step follows:

`Trigger -> Context -> Decision -> Action -> Result -> Next trigger`

`ProcessEngine` coordinates the step. `StateMachine` owns allowed transitions. `DecisionRouter` separates deterministic rules, future AI judgment, and human approval. Every received trigger and resulting decision/state change is appended to the case history. See [the architecture guide](docs/architecture.md) and [product specification](docs/product-spec.md).

## Repository structure

```text
config/       Business DNA example and schema
docs/         Product and architecture documentation
migrations/   Reproducible Alembic database migrations
src/api/      FastAPI application, contracts, dependencies, and routes
src/domain/   Domain types and state-transition rules
src/engine/   Decision routing and process orchestration
src/persistence/ Repository protocols and SQLAlchemy adapters
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

## Local PostgreSQL, migrations, and API

Copy the environment template, start PostgreSQL, migrate the database, and explicitly seed the non-production example tenant:

```bash
cp .env.example .env
docker compose up -d postgres
export DATABASE_URL='postgresql+psycopg://ai_process_engine:local_development_only@localhost:5433/ai_process_engine'
export APP_ENV=development
alembic upgrade head
python examples/seed_example_business.py
uvicorn src.api.app:app --reload
```

The API is available at `http://localhost:8000`, Swagger UI at `http://localhost:8000/docs`, liveness at `/health`, and database readiness at `/ready`. `DATABASE_URL` is mandatory; runtime startup never falls back to an in-memory database. Create schema revisions with `alembic revision --autogenerate -m "description"`, inspect them, and apply them with `alembic upgrade head`. Production schema creation must use Alembic, not `Base.metadata.create_all()`.

To run PostgreSQL and the API together, use `docker compose up --build`. The app waits for healthy PostgreSQL and runs `alembic upgrade head` before Uvicorn. Seed explicitly with `docker compose exec app python examples/seed_example_business.py`. The seed helper is idempotent and refuses to run unless `APP_ENV` is explicitly `development` or `local`. `POSTGRES_PORT` and `APP_PORT` control host ports; container-to-container database traffic always uses port 5432.

Submit a message after seeding:

```bash
curl -X POST http://localhost:8000/api/v1/businesses/acme-home-services/messages \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: manual-check-1' \
  -d '{"channel":"sms","external_message_id":"manual-1","message":"I need a diagnostic visit in 60601","timestamp":"2026-08-11T08:00:00Z","customer_name":"Ada","phone":"+13125550100"}'
```

The response includes `business_id`, stable case and lead IDs, `current_state`, a replay indicator, any customer question, `requires_human`, and a qualification summary. Reusing the same message identity and content returns the stored result; changing its fingerprint returns HTTP 409.

Fast tests use isolated file-backed SQLite databases through the same PostgreSQL-compatible repository code. PostgreSQL concurrency tests require a dedicated migrated test database:

```bash
export TEST_DATABASE_URL="$DATABASE_URL"
pytest -m postgresql
```

Do not point `TEST_DATABASE_URL` at production. The current integration tests create uniquely named tenant records but are intended for a disposable development/test database.

## Persistence guarantees

Every tenant-owned repository lookup requires `business_id`, and composite foreign keys prevent cases and events from crossing tenant ownership. Intake runs inside one Unit of Work: the database message claim, lead/case writes, audit events, state transition, and stored result commit or roll back together.

`processed_messages` has a composite primary key over business, channel, and external message ID. On PostgreSQL, a transaction-scoped advisory lock derived from that full identity serializes competing claims across workers until the winning transaction commits or rolls back. The composite primary key remains the authoritative uniqueness constraint, and `INSERT ... ON CONFLICT DO NOTHING RETURNING` identifies the claim owner. An identical fingerprint returns the stored result; a different fingerprint raises an explicit collision. Transaction-scoped locks are released automatically on commit, rollback, or connection loss, so an abandoned worker cannot leave a permanent process-local lock. Case updates use an integer version in the `UPDATE` predicate, so a stale worker receives `StaleCaseError` and its transaction—including candidate events—rolls back.

## Next milestone

Add authentication and authorization around the tenant routes, then introduce an action-executor boundary with an outbox. Real integrations and an LLM provider remain later milestones.
