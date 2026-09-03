# Flywheel Demand

Flywheel Demand is a separate product: a deterministic attract-to-inquiry engine. It analyzes audience, locks positioning, publishes attraction content or permission-based mailings, and stops when the person inquires.

This folder is the Demand product. It is kept next to Flywheel so the handoff
contract and Billing add-on can land together; it does not import Flywheel
and is meant to be its own GitHub repository.

Subscription is **not** sold here. The owner subscribes to Demand on the Flywheel Billing page. After an inquiry, Demand posts inbound JSON to Flywheel, which opens a process-engine case at `NEW_LEAD`.

This repository does not contain the lead-to-sale engine. Cold outreach and purchased lists are out of scope.

## Boundary

```text
Flywheel Demand                         Flywheel (billing + process engine)
audience → positioning → content/mail → inquiry JSON → NEW_LEAD → … → WON
```

## Run tests

```bash
python -m pip install -r requirements.txt
python -m pytest
```

## Local demo

```bash
PYTHONPATH=. python examples/demand_funnel_demo.py
```

## Docs

- [Product foundation](docs/demand/00-product-foundation.md)
- [Sources](docs/demand/01-market-sources.md)
- [Architecture](docs/demand/02-architecture.md)
- [Handoff contract](docs/demand/03-handoff-contract.md)
