# Flywheel Demand — handoff contract

Demand ends when a person inquires. The Business Process Engine starts at `NEW_LEAD`. This file is the interface between those products.

## Payload

`InquiryHandoff` (`src/demand/domain/handoff.py`) is the Demand-side record. Required fields: `business_id`, `prospect_id`, `campaign_id`, `channel`, `inquiry_text`, `event_id`, `handoff_id`, timezone-aware `occurred_at`. Identity and SMS consent are optional and pass through when present.

`source` is always `flywheel_demand`. `entry_state` is always `NEW_LEAD`. Demand has no authority to open a case in `QUALIFYING`, `QUALIFIED`, or any commercial state.

## Mapping to intake

`to_incoming_message()` produces `IncomingMessage` with:

| Handoff | IncomingMessage |
| --- | --- |
| `business_id` | `business_id` |
| `channel` | `channel` (`webchat`, `email`, or `sms`) |
| `demand:{prospect_id}:{event_id}` | `external_message_id` |
| `inquiry_text` | `raw_text` |
| `occurred_at` | `timestamp` |
| name / email / phone | same |
| SMS consent ledger | `sms_consent` |

Attribution (`campaign_id`, brief, sequence step) stays on the handoff. Product 1 does not need it to run the cycle. A later persistence slice may copy a subset onto `Lead.attributes` without changing qualification rules.

## Adapter

`DemandHandoffAdapter.deliver(handoff)` is the only supported way to cross the boundary in-process. It rejects any entry state other than `NEW_LEAD`, then calls `LeadIntakeService.receive`.

## What Demand must not do after handoff

- continue loyalty sends to a `HANDED_OFF` prospect;
- qualify, book, quote, or follow up on the deal;
- mutate process-engine state except by sending that one inbound message;
- invent inquiry text. The payload is the person's own message.
