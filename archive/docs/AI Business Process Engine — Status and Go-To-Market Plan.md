# AI Business Process Engine — status and go\-to\-market plan

*Prepared August 12, 2026, based on a direct inspection of the `ai-business-process-engine` repository (commit `daefb7c`, plus uncommitted Milestone 7 work) and the goal of first revenue within one month and $50,000/month profit within six months.*

> **Historical snapshot — superseded.** This document describes the repository as it existed in August 2026 and is retained for planning history. Authentication, self-serve onboarding, the staff dashboard, Lemon Squeezy billing, production deployment, and optional Twilio SMS delivery have since been implemented. Statements below that say those capabilities are absent must not be used as current product status.

## 1\. What's actually built

Seven milestones of backend engineering are genuinely solid. The codebase has a deterministic state machine covering the full lead\-to\-cash lifecycle, an event\-driven process engine with append\-only audit history and idempotency, tenant\-scoped PostgreSQL persistence with optimistic concurrency and advisory\-lock coordination for cross\-worker races, an OpenAI\-backed intent extraction layer that is treated as untrusted advisory input rather than a decision\-maker, a durable multi\-turn conversation layer with a framework\-free embeddable website widget, and a deterministic booking/quoting/payment\-preparation workflow with timezone\- and Decimal\-safe pricing. 144 tests pass, including real PostgreSQL concurrency tests. This is materially more rigor than most early\-stage SaaS backends have at this stage — rollback safety, tenant isolation, and audit trails are already production\-grade concerns that most startups bolt on only after an incident.

Two things are worth flagging immediately, before anything else:

**Milestone 7 is not committed.** The booking/quoting/payment work exists only as uncommitted changes on your machine. It should be finished and pushed before any further work builds on top of it.

**A `front/` directory with seven React/JSX files exists but is untracked and disconnected.** A landing page, an onboarding wizard, a leads dashboard, and a conversation\-detail view have been designed (visually polished, with a clear "speed to lead" positioning already baked into the copy — *"Every lead gets answered. Every step gets logged."*) but none of them are wired to the API, there's no build tooling (no `package.json`), and none of it runs.

## 2\. What is missing — and it is the majority of what makes this a sellable product

The honest gap is this: the engine can run one correctly hand\-configured tenant's website chat end\-to\-end. It cannot yet be found, signed up for, configured, or paid for by a business owner without an engineer's help. Specifically, none of the following exist in the codebase today:

**Authentication and authorization.** Every milestone's documentation explicitly defers this. There is no login, no session, no way for a business owner to access their own data — `business_id` in the URL provides tenant *scoping*, not tenant *authentication*. Anyone who knows or guesses a business ID can currently query its public routes.

**Billing.** `PaymentRequest` records are prepared internally but no money is ever collected — there is no Stripe integration, no subscription, no invoice, no way for you to get paid by a tenant, let alone for a tenant's customers to pay them.

**Self\-serve onboarding.** Business DNA — the JSON configuration that defines a tenant's services, pricing, service area, and rules — is currently authored by hand and validated against a schema. There is no signup flow, no wizard, no API endpoint that creates a new tenant. The `business_dna_onboarding.jsx` mockup implies the intended shape of this, but it isn't connected to anything.

**Real outbound delivery.** The only channel that actually works end\-to\-end is the embedded website widget. SMS, email, and WhatsApp are modeled in the domain layer (channel enums, `CustomerResponse` objects) but nothing dispatches them — no Twilio, no SendGrid, no messaging provider integration exists anywhere in `src/`. For a home\-services vertical where a large share of leads come by phone call or text, this is a significant gap.

**Production deployment.** What exists is a local Docker Compose file for development. There's no hosted environment, no domain, no TLS, no managed database, nothing a real customer's website could point a `<script>` tag at today.

**A working dashboard.** The `leads-dashboard.jsx` and `conversation-detail.jsx` mockups describe what a business owner needs to see (their leads, conversations, bookings) but there is no live version of this — a paying customer currently has no way to see their own data except by asking you to query the database.

None of this is a criticism of the engineering so far — it's a description of the normal shape of a project that optimized for correctness\-first backend architecture before commercialization. But it changes what "first revenue in a month" has to mean.

## 3\. Reality check on the timeline

**First revenue within a month is achievable — but not through a self\-serve funnel**, because self\-serve requires billing, auth, and onboarding automation that don't exist yet and can't be safely built in days. The realistic path to a first paying customer in the next few weeks is a concierge motion: you (or a founder) hand\-pick two or three home\-services businesses, hand\-configure their Business DNA the same way the example tenant is configured today, embed the widget on their site manually, and invoice them directly or send a Stripe Payment Link outside the app. This validates willingness to pay without waiting on Milestone 8.

**$50,000/month profit within six months is an aggressive target that deserves a clear\-eyed unit\-economics check**, not a discouragement — just a plan grounded in real numbers rather than the number itself.

| Price per customer/month | Customers needed for $50K MRR |
| --- | --- |
| $150 | \~334 |
| $250 | \~200 |
| $350 | \~143 |
| $500 (higher tier \+ setup fee) | \~100 |

Getting to 100–300 paying local home\-services businesses in six months, starting from zero, with no proven acquisition channel, no self\-serve product yet, and (most likely) no dedicated sales team, is a very high bar — home\-services SMB owners are notoriously hard to reach digitally and slow to adopt new software regardless of how good the product is. It is not impossible, but it depends entirely on finding a distribution channel that scales faster than one\-by\-one outbound (see §5). A more defensible near\-term milestone is **10–20 paying pilot customers by month two** (roughly $2,000–$5,000 MRR at a $200–$300 price point), used to prove the conversion story, refine pricing, and decide by month three or four whether the growth curve realistically bends toward $50K by month six or more realistically by month nine to twelve. I'd rather give you a plan that gets you to real revenue on a real trajectory than a plan that quietly assumes numbers that don't hold up.

## 4\. Technical roadmap — the highest\-leverage work now

**This week — close out the foundation.** Commit and push Milestone 7. Decide and lock the initial ICP and pricing model (§5) before building anything else, since it determines what the onboarding wizard needs to ask for.

**Weeks 1–4 — "Milestone 8: sellable, not just runnable."** This is the single most important phase, because every dollar of marketing spent before it is wasted:

- Stripe subscription billing (Checkout \+ customer portal is enough at this stage — no need to build custom billing UI).
- Minimal authentication for business owners (a hosted auth provider like Clerk or Auth0 is faster and safer here than building it in\-house) gating a small staff area.
- Wire `leads-dashboard.jsx` and `conversation-detail.jsx` to the existing API so a paying customer can see their own leads and conversations — this alone converts the product from "a demo you run for someone" into "a tool they log into."
- A self\-serve Business DNA onboarding wizard (wiring `business_dna_onboarding.jsx` to a new tenant\-creation endpoint) that turns hand\-edited JSON into a form a business owner can fill out in fifteen minutes.
- Production deployment — a small managed Postgres plus a single app instance (Render, Fly.io, or similar) is sufficient at this scale; this doesn't need to be elaborate yet.
- Real outbound delivery for at least SMS via Twilio, since it's likely the highest\-value channel for this vertical and currently doesn't exist at all.

**Months 2–3 — scale\-readiness.** Replace the process\-local rate limiter with a shared one (Redis) before running multiple app workers in production, add an outbox\-based delivery boundary, integrate a real calendar (Google Calendar, or a field\-service platform API) so bookings sync outward, and turn `PaymentRequest` into an actual Stripe charge rather than an internal\-only record.

**Months 3–6 — iterate on real usage.** Expand channels (WhatsApp, email), build a lightweight reporting view for tenants (leads captured, response time, conversion rate — this becomes your best marketing material), and build a referral or reseller mechanism once a few pilots are converting well.

## 5\. Go\-to\-market and marketing strategy

**Ideal customer profile.** Local home\-services businesses — HVAC, plumbing, electrical, garage door, pest control — with roughly 2–15 staff, who get inbound leads by phone, form, or Google but respond slowly enough to lose them. This is not a guess: it's the exact scenario already modeled in your seed data and demo (a customer messages about a rattling furnace and gets an immediate, qualifying reply). That's a strong, ready\-made proof point.

**Positioning.** The landing\-page draft already has the right instinct: speed\-to\-lead plus a full audit trail, positioned against the fear of an unreviewable AI black box (*"Every decision your engine makes is deterministic, reviewable, and reversible."*) That trust framing matters more in this vertical than in most, because these owners are used to being burned by software that "does something with their leads" they can't inspect.

**Pricing.** Recommend a flat $199–$349/month subscription with no setup fee and a 14\-day trial once billing exists — simple enough for a non\-technical owner to say yes to on a phone call. For the very first pilots, before billing is built, offer free or heavily discounted access explicitly in exchange for a testimonial and the right to use their before/after numbers as a case study; that case study is your best future marketing asset. A second, higher\-value pricing motion — a per\-booked\-job success fee layered on top once trust is established — is worth revisiting in month four or five once you have real conversion data, but is not the right model to lead with while you're still proving the product.

**Acquisition channels, ranked by realistic speed\-to\-revenue in month one:**

Direct founder\-led outbound is the fastest path to the first dollar: identify 100–200 local home\-services businesses (Google Maps and Yelp listings are enough to start), call or message a sample of them to test their actual response time, and lead with that specific evidence ("we called five plumbers in your area, average reply time was four hours — here's what a customer would get from you in under a minute instead") when reaching out to owners. This is slow per\-customer but requires zero product beyond what exists today.

Trade\-association and local Facebook\-group presence is the second channel worth working in parallel — these groups are where local contractors already congregate, and a genuinely useful post (not an ad) plus a free\-pilot offer travels well in tight\-knit trade communities.

Partnerships are the channel most likely to let this scale past founder\-led 1:1 sales, and should be pursued starting in parallel, not after: web/marketing agencies that already serve local trades, and referral relationships with field\-service software resellers (Housecall Pro, Jobber, ServiceTitan's partner ecosystems) can multiply reach without a sales team, since they already have trusted relationships with exactly this ICP.

Content and SEO ("speed to lead" articles, real case studies from pilots) is a legitimate long\-term channel but has a three\-to\-six\-month payoff horizon and shouldn't be counted on for early revenue.

Paid ads are **not recommended for month one** — there's no proven landing page, no billing to convert a click into a customer, and no CAC data yet to know if it's economical. Revisit once a pilot has a clear before/after story to use as ad creative.

**The eventual self\-serve funnel**, once Milestone 8 ships: landing page → free trial signup with card capture → onboarding wizard → widget embed snippet → a test message to prove it works → an in\-app nudge to put the real widget live. Everything in `front/` already sketches this path; it just needs to be built and connected.

## 6\. Recommended next steps, in order

Finish and push Milestone 7 so nothing further builds on uncommitted work. Lock the ICP and pricing model this week, since it shapes what the onboarding wizard collects. Start manual outbound to twenty or thirty candidate businesses immediately, in parallel with engineering — the current widget is good enough to run a real pilot on a hand\-configured tenant today, so first revenue doesn't need to wait for self\-serve billing. Treat Stripe billing, minimal auth, and the onboarding wizard as the one non\-negotiable engineering sprint before any marketing spend, because every customer acquired before that exists has to be onboarded and invoiced by hand. Use the first two or three pilot customers' real before/after numbers as the foundation of both your case studies and your realistic six\-month forecast.
