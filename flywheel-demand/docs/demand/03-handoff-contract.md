# Flywheel Demand — handoff contract

Demand ends when a person inquires. Flywheel starts at `NEW_LEAD`. Subscription for Demand is purchased on Flywheel Billing, not in this product.

## Payload

`InquiryHandoff.to_intake_payload()` is the Demand-side JSON. Required fields: `business_id`, `prospect_id`, `campaign_id`, `channel`, `inquiry_text` as `raw_text`, `external_message_id`, timezone-aware `timestamp`. Identity and SMS consent pass through when present.

`source` is always `flywheel_demand`. `entry_state` is always `NEW_LEAD`.

## Flywheel endpoint

`POST /api/v1/businesses/{business_id}/demand/inquiries`

- Header `X-Internal-Task-Secret` (the same secret Flywheel uses for internal sweeps).
- Flywheel rejects the call unless that business has an active Demand add-on (`has_demand_access`).
- Flywheel maps the JSON to `IncomingMessage` and runs `LeadIntakeService.receive`.

## What Demand must not do after handoff

- continue loyalty sends to a `HANDED_OFF` prospect;
- qualify, book, quote, or follow up on the deal;
- invent inquiry text.
