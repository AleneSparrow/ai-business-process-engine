# Flywheel Demand

Flywheel Demand is a **separate product**. Its engine lives in [`flywheel-demand/`](../../flywheel-demand/).

This Flywheel repository:

- sells the Demand subscription on the Billing page (Lemon Squeezy add-on, `has_demand_access`);
- accepts inquiry JSON at `POST /api/v1/businesses/{business_id}/demand/inquiries` (internal secret + active add-on);
- opens a process-engine case at `NEW_LEAD`.

It does not contain Marketing DNA, campaign/prospect state machines, or attraction content. Those stay in the Demand product so this engine remains “from inquiry to sale.”

Product docs: [`flywheel-demand/docs/demand/`](../../flywheel-demand/docs/demand/).
Handoff contract: [`flywheel-demand/docs/demand/03-handoff-contract.md`](../../flywheel-demand/docs/demand/03-handoff-contract.md).
