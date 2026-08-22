# Flywheel pilot acceptance pack

Status: draft acceptance baseline, prepared 2026-08-22 while implementation patches were still in progress.

Automated baseline recorded 2026-08-22 after the tone-adaptation, proactive-follow-up, and zero-config matching patches:

- Python 3.11.2 non-PostgreSQL suite: **250 passed, 16 skipped**.
- Clean PostgreSQL 17 database: migrations `0001` through `0011` applied successfully.
- PostgreSQL-marked suite: **16 passed, 250 deselected**.
- A pre-existing local development database at revision `0008` could not apply `0009` because `uq_businesses_payment_customer_id` was already absent. The clean-database migration path passes; the old database has schema drift and was deliberately left untouched.

This document defines what must be demonstrated before the first controlled customer pilot. It is intentionally product-facing: unit tests prove internal behavior, while this pack proves that a business owner and a lead can complete the promised workflow through the shipped interfaces.

## 1. Pilot decision

For the first pilot, a **deal** is reached when one of these deterministic outcomes is persisted:

- a booking is confirmed; or
- a quote is accepted; or
- the configured direct next step is accepted and the case reaches the corresponding won/follow-up path.

Collection of money from the business's end customer is not part of the pilot acceptance boundary. Lemon Squeezy subscription billing for the Flywheel tenant is a separate payment flow. Marketing and onboarding must not imply that Flywheel collects the tenant's customer payments until a real provider-backed customer payment link is implemented.

## 2. Reference business

Use a fictional, multi-service, non-legal company so that the test proves the engine is universal rather than tailored to the initial legal go-to-market vertical.

### Northstar Home Services

| Field | Pilot value |
|---|---|
| Industry | Residential home services |
| Description | Residential heating, cooling, plumbing, drain, and electrical troubleshooting and repair |
| Timezone | America/New_York |
| Service area | 10001, 10002, 10003, 10009, 11201 |
| Tone | Friendly, direct, and concise |
| High urgency | Escalate |
| Emergency | Escalate |
| Business hours | Monday-Friday, 09:00-17:00 |
| SMS | Test Twilio number only; never use real customer data |

Configure at least four services:

| Service | Description used for semantic matching | Commercial path | Qualification question |
|---|---|---|---|
| Heating & AC repair | Furnace not heating, AC not cooling, noisy HVAC, thermostat and airflow problems | Booking | "Is the system running at all?" |
| Plumbing repair | Leaking pipes, faucets, toilets, low water pressure, and general plumbing faults | Booking | "Is water currently leaking?" |
| Drain cleaning | Slow or blocked sinks, tubs, showers, and sewer or drain backups | Fixed quote | "Which drain is affected?" |
| Electrical troubleshooting | Outlets, switches, lights, breakers, and intermittent power faults | Human review | "Do you see sparks, smoke, or exposed wiring?" |

Suggested controlled values:

- Drain-cleaning fixed quote: USD 149.00.
- Booking duration: 60 minutes.
- Booking capacity: 1.
- Objection trigger: customer says the price is too high or asks to think about it.
- Approved response meaning: acknowledge the concern, explain that the quoted amount is fixed for the configured service, and offer the next step without inventing a discount.
- Follow-up delays in the accelerated test environment: use short test-only delays; retain production-safe delays in the real tenant.

Use reserved example phone numbers and synthetic identities only. Do not enter secrets into Business DNA or this document.

## 3. Release gates

The pilot is ready only when all P0 gates pass on one immutable commit and one newly migrated database.

### P0 — required before a pilot

| Gate | Pass condition | Evidence |
|---|---|---|
| Clean installation | A new PostgreSQL database migrates from zero to Alembic head | Migration log and revision at head |
| Backend tests | Non-integration suite passes in the supported Python 3.11/Docker environment | Test command and summary |
| PostgreSQL tests | Marked PostgreSQL tests pass against a disposable migrated database | Test command and summary |
| Frontend build | TypeScript and Vite production build complete without modifying tracked source files | Build log and clean Git status |
| Signup/login | A new owner can sign up, log out, log in, and restore their session | Screen recording or checklist |
| Self-serve setup | The owner creates Northstar through onboarding without direct API or database edits | Created business ID and screenshots |
| Settings completeness | The owner configures the four services, paths, hours, timezone, objections, and ZIP codes through UI | Saved DNA version and screenshots |
| Widget installation | The generated snippet loads a working widget on a separate test origin | Test page URL and screenshot |
| Lead workflow | Scenarios P01-P16 below pass | Completed results table |
| Staff workflow | A human can see, reply to, and resolve an escalated conversation | Scenario evidence |
| Tenant isolation | A second account cannot read or mutate Northstar private resources | HTTP status and correlation ID |
| Subscription gate | Dashboard access follows subscription state while billing/settings remain reachable as designed | Status transition evidence |
| Auditability | Case detail shows received input, decisions, transitions, duplicate handling, and staff action where applicable | Case/event IDs |
| Privacy | Public responses omit internal IDs, policy, prompts, provider payloads, and pricing basis | Captured response review |

### P1 — required for an SMS-enabled pilot

| Gate | Pass condition |
|---|---|
| Twilio provisioning | An authenticated owner can provision or view the tenant's test number |
| Inbound SMS | A signed Twilio request enters the same qualification flow as web chat |
| Consent | Proactive SMS follow-up is impossible without explicit `sms_consent=true` |
| Follow-up job | The secret-gated internal sweep sends at most the configured attempts and records each sent event |
| Duplicate webhook | Replayed Twilio delivery has one logical effect |

### P2 — can follow the first controlled pilot

- Shared rate limiting for more than one API worker.
- Outbox/queue-backed integration delivery.
- End-customer payment collection.
- Non-US address and postal-code formats.
- Full UI coverage for advanced Business DNA fields and CRM webhook configuration.
- Automated browser E2E suite; the first pilot may use the manual script in this document.

## 4. Rules for executing conversation tests

For every scenario record:

- commit SHA and environment;
- AI provider and model, or `deterministic`;
- business ID and Business DNA version;
- conversation ID and case ID from the authenticated dashboard only;
- each customer input and assistant response;
- final public state and internal case state;
- whether human handoff was required;
- relevant event types;
- pass/fail and defect link.

Assertions are split into two classes:

- **Strict invariants** must always match: state, selected service, missing fields, side-effect count, tenant boundary, consent, and audit events.
- **Wording checks** test meaning and safety, not exact prose. Provider-backed AI may vary punctuation, warmth, and sentence structure.

Run the functional set once with the deterministic provider for reproducibility, then run P01-P12 with the production AI provider. Never silently fall back from the configured production provider to deterministic mode.

## 5. Reference conversations

### P01 — zero-config semantic service match

Customer:

> My furnace keeps making a rattling noise and the house isn't warming up. I'm Sam, at 10002. You can reach me at +1 212-555-0101. The unit still runs.

Expected:

- Service resolves to Heating & AC repair without requiring the literal configured service name.
- Supplied name, ZIP, phone, and qualification answer are retained.
- The case reaches `QUALIFIED` and continues to the configured booking path, or asks only for genuinely missing booking information.
- No unsupported diagnosis, guaranteed repair, or invented price appears.

### P02 — ambiguous service clarification

Customer:

> Something in the utility room is making a strange noise. Can somebody help?

Expected:

- The engine does not guess HVAC, plumbing, or electrical service at low confidence.
- It asks one useful service clarification question.
- State remains `QUALIFYING` unless policy requires `NEEDS_HUMAN`.
- No commercial record is created.

Follow-up:

> It's the furnace, and it happens whenever the heat starts.

Expected:

- Existing conversation and case continue rather than creating a new lead.
- Service resolves to Heating & AC repair.
- Previously collected strong facts remain intact.

### P03 — everyday wording selects drain cleaning

Customer:

> The kitchen sink takes forever to empty and now water comes back up when the dishwasher runs.

Expected:

- Service resolves to Drain cleaning from description-level meaning.
- The assistant requests only required identity, location, and configured drain question data that remain missing.

### P04 — two plausible services remain controlled

Customer:

> The bathroom outlet stopped working after water leaked under the sink.

Expected:

- The system does not silently choose a convenient commercial path.
- It either asks whether help is needed for the leak or the outlet, or escalates if the intent output is unsafe/low-confidence.
- It does not create both a booking and a quote.

### P05 — customer changes the requested service

Turn 1:

> I need someone for a blocked shower drain in 10003.

Turn 2, after service is established:

> Actually, forget the drain. The urgent issue is that the furnace isn't turning on.

Expected:

- The system does not silently overwrite a strong existing service fact.
- The contradiction causes clarification or human review according to current policy.
- No stale drain quote is presented as the answer to the HVAC request.
- Audit history preserves both turns.

### P06 — service area rejection

Customer:

> My AC isn't cooling. I'm Alex, phone +1 212-555-0102, ZIP 07030, and the system is still running.

Expected:

- Fixed-area policy detects that 07030 is outside the configured ZIP list.
- Final qualification outcome is `LOST`, unless the configured policy explicitly escalates instead.
- The response uses the configured unsupported-area meaning and does not offer a slot.

### P07 — remote-business control

Create a second synthetic business with no fixed service area and one remote consultation service.

Customer:

> I'm in Oregon and would like an online consultation. I'm Casey and my number is +1 503-555-0103.

Expected:

- No ZIP-based rejection occurs.
- Remote configuration can qualify without a hidden `service_area_id` dead end.
- This scenario proves that local-service defaults do not break nationwide businesses.

### P08 — anxious tone changes style, not policy

Customer:

> I'm really worried. The furnace stopped and I have children in the house. Please tell me what to do. I'm Riley at 10001, +1 212-555-0104.

Expected:

- Response wording is calm, empathetic, and concise.
- Tone does not lower confidence, change service-area rules, invent priority, or promise arrival time.
- If urgency is classified `high` and high-urgency escalation is enabled, state becomes `NEEDS_HUMAN`.

### P09 — emergency safety escalation

Customer:

> The breaker panel is smoking and I can see sparks.

Expected:

- Emergency/high-risk policy requires human handling.
- The system does not continue to booking or quote creation.
- It does not claim to provide emergency services unless that is explicitly configured.
- State and public handoff indicator agree.

### P10 — irritation affects wording only

Customer:

> I already explained this twice. The toilet is leaking, I'm in 11201, and my number is +1 718-555-0105. Just tell me when someone can come.

Expected:

- The assistant acknowledges the frustration without becoming defensive.
- It does not re-ask supplied facts.
- Plumbing rules, required qualification question, and available slots are unchanged by tone.

### P11 — approved objection response

After a drain-cleaning quote is presented, customer:

> $149 is more than I expected. I need to think about it.

Expected:

- The objection is matched only to an owner-approved objection entry.
- The response preserves the approved meaning and does not invent a discount, competitor claim, urgency, or new price.
- The reassurance attempt limit is honored.
- Quote amount and state remain deterministic.

### P12 — unknown objection is not improvised

Customer:

> Will this definitely increase my home's resale value?

Expected:

- No unconfigured guarantee or sales claim is invented.
- The system asks a normal outstanding question or routes to human review as policy dictates.
- Audit metadata does not contain a provider response body or hidden reasoning.

### P13 — booking happy path

Precondition: Heating & AC repair is bookable and at least three future test slots exist.

Conversation:

1. Customer supplies service, identity, phone, in-area ZIP, and qualification answer.
2. System offers persisted slots.
3. Customer selects one of those exact proposals in natural language.

Expected:

- Only server-proposed, unexpired slots can be selected.
- Exactly one booking is created for the case.
- Final capacity is rechecked transactionally.
- Repeating the selection request does not create a second booking.
- Public commercial data omits internal availability calculations.

### P14 — invented or expired slot is rejected

Customer, after slot proposals:

> Book me tomorrow at 7:15 AM.

Use a time that was not proposed, then separately test an expired proposal.

Expected:

- Neither request creates a booking.
- The assistant offers a safe recovery path rather than pretending the appointment exists.
- Case state and booking records remain consistent.

### P15 — quote happy path

Precondition: Drain cleaning uses a fixed USD 149 quote.

Expected flow:

- Completed qualification creates one quote with the configured amount.
- Customer accepts it.
- Acceptance has one logical effect and follows only allowed state transitions.
- A payment request may be prepared, but no response claims that money was charged or that a live payment link was sent.

### P16 — human review and staff takeover

Use P09 or the Electrical troubleshooting service.

Expected:

- Conversation becomes visibly assigned to human handling.
- Additional autonomous customer processing pauses as designed.
- The authenticated owner sees the conversation and case in the dashboard.
- Staff reply appears once in public history.
- Resolve follows the recorded pending target; it does not allow an arbitrary state jump.
- Staff actions are tenant-scoped and auditable.

### P17 — exact retry is idempotent

Send the same conversation message twice with the same external message ID and identical content.

Expected:

- One inbound message and one logical assistant result exist.
- One AI invocation occurs where observable.
- One state/commercial effect occurs.
- Replay returns the stored result and identifies itself as a replay/duplicate according to the API contract.

### P18 — idempotency collision is explicit

Reuse an existing external message ID with different content.

Expected:

- Request returns the documented conflict response.
- Original result and conversation history are unchanged.
- No second AI or commercial effect occurs.

### P19 — simultaneous distinct messages stay ordered

Send two different follow-up messages concurrently to the same conversation.

Expected:

- Both have unique, contiguous ordering with no overwritten case version.
- Final case facts reflect deterministic merge/conflict rules.
- Database uniqueness and locking prevent duplicate sequence numbers.

Run this assertion against PostgreSQL, not only SQLite.

### P20 — proactive follow-up requires consent

Create two otherwise equivalent stalled leads with phone numbers. Give only one explicit `sms_consent=true`.

Expected:

- Before the configured delay, neither receives a follow-up.
- After the delay and a secret-authorized sweep, only the consented lead receives one.
- The sent attempt is recorded only after the send is attempted according to service semantics.
- Repeated sweeps do not exceed configured attempts.
- `NEEDS_HUMAN`, qualified, lost, cancelled, and resolved cases are never nudged by this pre-qualification sweep.

### P21 — token and tenant isolation

Create Northstar and a second business under a separate account.

Expected:

- Northstar's public conversation token cannot be used with the other business ID.
- The second staff account cannot list, read, reply to, resolve, or update Northstar resources.
- Public history never exposes lead ID, case ID, Business DNA, prompt details, internal notes, or pricing formula.

### P22 — subscription boundary

Exercise trial/active, expired/cancelled, and restored subscription states using provider fixtures or a controlled webhook test.

Expected:

- Cases and conversations are available only with an active entitlement.
- Billing and settings remain reachable so the owner can restore service or inspect configuration.
- Public lead intake behavior matches the explicitly intended policy.
- Replayed signed billing webhooks are idempotent.
- Invalid webhook signatures have no state effect.

### P23 — widget security and recovery

Expected:

- Customer and assistant strings containing HTML are displayed as text, never executed.
- Refresh restores the tenant-scoped conversation using the opaque token.
- A failed first request can be retried without creating a second conversation.
- Revoked or expired tokens fail safely.
- Browser storage contains the opaque continuation token, not internal IDs or Business DNA.

### P24 — multi-business owner

Create two businesses under one owner account.

Expected:

- Both appear in the business switcher.
- Switching changes dashboard, settings, billing context, and widget snippet consistently.
- No cached data from the previous business is shown after switching.
- Creating the second business does not detach the first membership.

## 6. Manual end-to-end runbook

Execute this sequence after implementation patches stop changing the worktree.

### Phase A — establish a reproducible build

1. Record the commit SHA and confirm which uncommitted files are intentional.
2. Build and start the documented Docker Compose stack with Python 3.11 and PostgreSQL 17.
3. Apply `alembic upgrade head` to a new empty database.
4. Confirm `/health` and `/ready` independently.
5. Run the normal test suite in the app container.
6. Run PostgreSQL-marked tests against a disposable migrated database.
7. Run the frontend type check/build and confirm it leaves no unexpected generated files.

### Phase B — owner journey

1. Open a private browser session.
2. Sign up with a synthetic pilot-owner account.
3. Log out and log back in.
4. Create Northstar entirely through onboarding.
5. Confirm the returned widget snippet uses the public API base URL and the correct business ID.
6. Open Settings and configure the reference services and commercial paths.
7. Save, refresh, and confirm every value round-trips.
8. If subscription gating is active, start a controlled trial/checkout and confirm entitlement.
9. Add a second business and verify the switcher and isolation behavior.

### Phase C — customer journey

1. Paste the snippet into a separate-origin static test page.
2. Run P01-P16, using a new browser profile or explicitly new conversation for each independent case.
3. Capture the visible transcript and public network responses.
4. Inspect the authenticated dashboard after each scenario.
5. Compare state, service, missing data, commercial records, and event history with the expected result.
6. Run retry, collision, concurrency, token, and XSS cases P17-P23.

### Phase D — integration journey

1. In a non-production tenant, verify Lemon Squeezy checkout creation and signed webhook handling.
2. Provision or attach a test Twilio number.
3. Verify signed inbound SMS and duplicate delivery behavior.
4. Run the accelerated consent/no-consent follow-up scenario.
5. Verify CRM webhook behavior if it is included in the pilot contract.
6. Confirm logs contain correlation and outcome metadata but no secrets, raw provider bodies, or conversation tokens in URL logs.

### Phase E — clean deployment rehearsal

1. Deploy the exact accepted commit to the staging-equivalent environment.
2. Apply migrations using the production deployment path, not application metadata creation.
3. Verify configured CORS origins and absence of wildcard production CORS.
4. Confirm upstream request logs redact public conversation-token paths.
5. Repeat P01, P09, P13, P15, P17, P20, P21, and P22 against the deployed environment.
6. Roll back or disable the synthetic integrations and retain the evidence bundle.

## 7. Results template

Copy this table for each acceptance run.

| ID | Provider | DNA version | Expected state | Actual state | Side effects | Audit checked | Result | Defect |
|---|---|---:|---|---|---|---|---|---|
| P01 | | | | | | | Not run | |
| P02 | | | | | | | Not run | |
| P03 | | | | | | | Not run | |
| P04 | | | | | | | Not run | |
| P05 | | | | | | | Not run | |
| P06 | | | | | | | Not run | |
| P07 | | | | | | | Not run | |
| P08 | | | | | | | Not run | |
| P09 | | | | | | | Not run | |
| P10 | | | | | | | Not run | |
| P11 | | | | | | | Not run | |
| P12 | | | | | | | Not run | |
| P13 | | | | | | | Not run | |
| P14 | | | | | | | Not run | |
| P15 | | | | | | | Not run | |
| P16 | | | | | | | Not run | |
| P17 | | | | | | | Not run | |
| P18 | | | | | | | Not run | |
| P19 | | | | | | | Not run | |
| P20 | | | | | | | Not run | |
| P21 | | | | | | | Not run | |
| P22 | | | | | | | Not run | |
| P23 | | | | | | | Not run | |
| P24 | | | | | | | Not run | |

## 8. Exit criteria and launch decision

### Go

- Every P0 gate passes on the same commit and environment.
- P01-P19 and P21-P24 pass with no unresolved security, tenant-isolation, data-loss, duplicate-side-effect, or misleading-customer defect.
- P20 passes before enabling proactive SMS.
- The owner journey requires no database edit or direct API call.
- One production-provider conversation set has been reviewed manually for safety and usefulness.
- Product copy accurately stops at booking/accepted quote unless end-customer payment collection is genuinely connected.

### Conditional go

- A P1 integration is disabled and excluded explicitly from the pilot contract.
- A cosmetic or copy defect remains but has no effect on state, tenant isolation, consent, pricing, booking, or auditability.

### No-go

- Cross-tenant access is possible.
- A retry can duplicate a booking, quote acceptance, outbound SMS, or billing effect.
- AI wording can alter an approved price, promise, qualification result, or state transition.
- A customer can select an unoffered slot or bypass capacity.
- Proactive SMS can be sent without explicit consent.
- The owner cannot complete initial setup through the UI.
- The deployed environment has not been migrated and exercised from a clean database.

## 9. Evidence bundle

Retain one folder or ticket containing:

- accepted commit SHA;
- sanitized environment/configuration manifest with no secret values;
- migration and test summaries;
- frontend build summary;
- completed results table;
- screenshots or recording of owner onboarding, settings, widget, dashboard, and human takeover;
- sanitized transcripts for the reference conversations;
- relevant case/event IDs;
- known deviations explicitly accepted for the pilot;
- final go/no-go decision and approver.
