# Очередь постов — недели 1–4

Все тексты ниже — **английский**, готовые к копированию. Статус всех: `DRAFT`.
Публикация только после `LINT_PASS` и вашего `APPROVED`.

Не добавлять эмодзи, хэштег-простыни и «Excited to announce».

Формат блока для линтера: заголовок `### ID`, поля, затем `---` и тело до
следующего `###`.

---

### LI-001
channel: linkedin
audience: both
pillar: builder
status: DRAFT
scheduled_for: week-1-tue

---

I'm Alena Vorobei. I'm building Flywheel.

Not a chatbot. Not a receptionist. Not a tool that takes a name and puts it in your inbox.

Flywheel is a deterministic engine that carries an inbound inquiry all the way to a booked job or an accepted quote — for any business, with no custom setup per company.

The model does not decide what to say. It rewrites wording inside a script the business already approved. State, qualification, booking, follow-up — that's the engine, not the prompt.

I'm shipping this in the open from the build, not from a launch party. If you want the short version of the loop: inquiry in, prepared deal out.

I'll post the architecture, the screens, and the parts that are still unfinished. The unfinished parts matter. That's how you can tell who is actually building it.

---

### LI-002
channel: linkedin
audience: both
pillar: cycle
status: DRAFT
scheduled_for: week-1-wed

---

Most AI tools sold to small businesses stop at the same sentence:

"Thanks — we'll get back to you."

That is not a sales cycle. That is a nicer voicemail.

The business still has to qualify the person, answer the price question, follow up when they go quiet, and book the work. That is where paid inquiries die.

Flywheel does not stop at capture. The same engine that answers also qualifies, follows up, and books — on a script the business approved, with an audit log of every step.

If a product hands the conversation back to you as a task, it did not close the loop. It created a queue.

I'm building the loop.

---

### LI-003
channel: linkedin
audience: scene
pillar: model
status: DRAFT
scheduled_for: week-1-thu

---

A design choice I will not reverse: the language model is not allowed to change case state.

In Flywheel, `decision_router` and `qualification_service` decide what happens next. The model extracts intent and rewrites wording that already exists in Business DNA. If the output doesn't pass the schema, it does not ship. If confidence is low, a human gets the case. If a message would require inventing a promise, there is no path for that promise to be generated.

This is slower to demo than "an agent that just handles it." It is also the only way I will put this in front of a real customer.

Agents that plan, reason, and then act are a category. I am not in that category. I am building a cycle that cannot improvise a price, a legal conclusion, or a booking that the rules did not allow.

If you are tired of watching an LLM talk itself into a side effect, you already understand the product.

---

### LI-004
channel: linkedin
audience: both
pillar: builder
status: DRAFT
scheduled_for: week-1-fri

---

Building in public, honestly, from the development stage — not from a polished launch.

What Flywheel already does:

- A full lead-to-deal state machine, not a chat wrapper
- Business DNA instead of custom code per company
- Website widget, staff UI, auth, billing for the SaaS itself
- An audit history of decisions, not a vibe

What it does not do yet, and I will not pretend otherwise:

- Collecting the end customer's money (the engine prepares a payment request; collection is not connected)
- Live proof on a multi-service non-legal tenant for tone and follow-up — that's the next honest test, not a slide

I would rather be early and specific than late and glossy. If you only show up on launch day, nobody can tell whether you built the thing.

I'll keep posting screens and decisions as they land.

---

### LI-005
channel: linkedin
audience: buyer
pillar: cycle
status: DRAFT
scheduled_for: week-2-tue

---

A useful number: in legal services, blended cost per lead sits around $649. In financial services, about $653. You already paid for that inquiry before anyone answered it.

Industry data on missed calls is ugly in every vertical, not just that one: most people who hit voicemail do not call back. Speed-to-respond still moves the probability of a conversation by orders of magnitude (the MIT lead-response work: minutes, not hours).

So the expensive failure is not "we need more marketing." It is: the inquiry arrived, and the cycle did not.

Flywheel is built for that hole. It answers, qualifies, handles the objections you approved, follows up, and books. You get a prepared matter or a booked job — not a task list of names.

$199/month on a 7-day trial. I am looking for owners who already get inbound demand and lose it after hours. If that's you, I'll send a two-minute walkthrough.

---

### LI-006
channel: linkedin
audience: scene
pillar: builder
status: DRAFT
scheduled_for: week-2-wed

---

Zero custom setup is a product requirement, not a slogan. Here is how Flywheel enforces it.

Every tenant is a Business DNA document: identity, services, prices, geography, hours, qualification questions, escalation, what the assistant is allowed to say. The Python in `src/` has no industry branch and no frozen vertical vocabulary. If a salon and a practice run on the same engine, that is the test. If I have to fork the code, I failed the test.

Onboarding is a form that writes DNA, not a services engagement.

I'll screen-record the DNA editor and a live conversation in the next video. If the setup needs me on a call to "configure your industry," the product is lying.

---

### LI-007
channel: linkedin
audience: both
pillar: cycle
status: DRAFT
scheduled_for: week-2-thu

---

Capture and a closed cycle are different products. The market keeps selling the first under the name of the second.

Capture: take a name, a number, a short message, dump it in an inbox. The owner still qualifies, still prices, still chases, still books.

Closed cycle: the same system moves the person through qualification, quote or booking, follow-up, and a terminal state — won, lost, or handed to a human when the rules say so.

I will not describe Flywheel as an intake product. Intake is the first miles. The engine is built for the rest of the road, including reactivation after a loss.

If a vendor's demo ends at "we'll notify your team," they built a receptionist with a nicer UI. Ask them what happens to the lead at 9pm, and who books the job.

---

### LI-008
channel: linkedin
audience: scene
pillar: model
status: DRAFT
scheduled_for: week-2-fri

---

Two 2026 stacks get mixed up in every pitch:

1. Deterministic workflows. Trigger, condition, action. Debuggable. Cheap. Bad at messy language.
2. LLM agents. They interpret, plan, and act. Good at messy language. Easy to let them write a side effect you cannot replay.

Flywheel is a hard split: language in a sandbox, state outside it.

Intent and wording can come from a model. Qualification, geography, price, capacity, and the next state cannot. Every transition is an explicit record. Replay the same message id and you do not get a second booking.

HubSpot-style agents inside a CRM will keep getting better at "figuring it out." That is not an argument for giving them the keys to promises and calendar capacity. It is an argument for keeping a cycle whose rules do not drift mid-conversation.

I am betting that SMBs who have been burned by a chatbot's improvisation will pay for the boring split.

---

### LI-009
channel: linkedin
audience: both
pillar: builder
status: DRAFT
scheduled_for: week-3-tue

---

The product is not a vertical. The first beachhead is. Flywheel has to survive that distinction.

I am starting conversations with solo practices in California and New York because the leads are expensive and disclosure is already law there. That is an entry, not a definition.

The same engine has to run a non-legal service business without a code fork. No lawyer vocabulary in `src/`. No hidden "if industry == …". If I cannot show that, the USP is a paragraph, not a product.

This week I'm posting a recording of one non-legal conversation on the same pipeline. If you sell a real-world service and you already get inbound inquiries, I want that as a design partner more than I want another slide about attorneys.

---

### LI-010
channel: linkedin
audience: buyer
pillar: cycle
status: DRAFT
scheduled_for: week-3-wed

---

I did not build a thing you implement for six weeks.

Starter is $199/month, 7-day trial, card on file, no charge until the trial ends. Setup is Business DNA in about twenty minutes: who you are, what you sell, where you work, what you ask, when a human should take over.

No developer. No prompt-engineering workshop. If the assistant needs a custom script written by my team to function, I have failed the self-serve test.

What you should see at the end of those twenty minutes: a widget on a page, a test inquiry, a path to a booked slot or a quote the rules allow — and a log of why it said what it said.

If you want the walkthrough instead of the form, say so. I will not invent a services layer to make the first week feel "white glove." The product has to stand up on its own. That's the flywheel.

---

### LI-011
channel: linkedin
audience: both
pillar: cycle
status: DRAFT
scheduled_for: week-3-thu

---

A boundary I will keep repeating, because the category is noisy:

Flywheel does not generate demand. It does not scrape lists. It does not write outbound prospecting sequences.

Someone already reached out — a form, a chat, a message. That's the start of the cycle. The engine's job is to not drop that person before a booked job or an accepted quote.

Generating demand is a different product, for later. If I blur that line, I am promising a factory I did not build.

If your problem is "nobody is inquiring," this is not the tool. If your problem is "they inquire and then nothing happens until morning," this is exactly the tool.

---

### LI-012
channel: linkedin
audience: scene
pillar: model
status: DRAFT
scheduled_for: week-3-fri

---

Audit is not a PDF you attach after a scare.

In Flywheel every accepted trigger, decision, state change, rejection, and duplicate is appended to the case history. Staff can see why the engine asked a question, why it booked, why it escalated. The customer-facing text is treated as untrusted in prompts and in the browser.

I built it this way because I will not ship a cycle I cannot replay.

If a vendor cannot show you the decision that produced a sentence, they are asking you to trust a prompt. That's fine for a draft. It is not fine for a price, a booking, or a promise.

I'll show the log next to the chat in a screen recording. The interesting part is not the UI. The interesting part is that the UI is reading an append-only history, not a chat transcript someone could edit.

---

### LI-013
channel: linkedin
audience: scene
pillar: builder
status: DRAFT
scheduled_for: week-4-tue

---

I am building a US product, in English, for US businesses, in public. The product is Flywheel.

The market is not "global SMB" as a slogan. Geography, pricing, disclosure, and the way owners buy are American. I will be in that conversation every week — on this profile, on X, on camera — while the engine is still being finished, not after a relocation montage.

If you work in SF or LA and you care about inbound cycles that don't let a model improvise side effects, you'll see the same person posting the same system. That continuity is the point. Hire-an-agency energy dies when the founder can open the repo and the dashboard in the same take.

I don't need a louder story. I need a dated trail of the build.

---

### LI-014
channel: linkedin
audience: both
pillar: cycle
status: DRAFT
scheduled_for: week-4-wed

---

There is a $29–$99 band of products that answer the phone and take a message. They are doing a real job. It is not this job.

A receptionist that never sleeps still ends at a task for the owner. Flywheel is priced at $199 / $499 because it is meant to replace the rest of the cycle — qualification, quote or booking, follow-up — not the greeting.

If a buyer compares me only to the cheapest answering bot, I have explained the product badly. The fair comparison is: staff time plus lost inquiries, or a tool that stops at capture.

I will not race a $49 product on price. I will keep drawing the line at "does the job get booked without you waking up."

---

### LI-015
channel: linkedin
audience: buyer
pillar: builder
status: DRAFT
scheduled_for: week-4-thu

---

Who I want as a Flywheel design partner:

- You already get inbound inquiries (site, chat, after-hours). You do not need me to invent demand.
- A single owner can say yes. Self-serve, not a committee.
- You will let me use before/after operational facts (response time, booked jobs, after-hours conversations) as a case — anonymized if you want.
- You will actually put the widget on a real page, not a staging graveyard.

Who I do not want yet:

- Teams that need multi-staff routing as the reason to buy (that tier is not the first honest sale)
- Anyone whose main ask is "make us more leads"
- Anyone who needs me to promise a conversion rate I have not measured

$199 Starter, 7-day trial. Reply "cycle" and I'll send the walkthrough. If it's a bad fit I will say so fast. That's cheaper for both of us than a polite maybe.

---

### LI-016
channel: linkedin
audience: scene
pillar: model
status: DRAFT
scheduled_for: week-4-fri

---

A pattern I keep seeing in agent pitches: the demo is a happy path where the model "just handles it," and the failure mode is a confident sentence that never should have been allowed to exist.

I don't argue with the demo. I ask three questions:

1. Can the model change a booking, a price, or a status on its own?
2. If I replay the same inbound id, do I get a second side effect?
3. Can a staff member point at the rule that produced the sentence?

If the answers are yes / maybe / not really, you have a language model with tools. You do not have a cycle.

Flywheel's boring answers: no; no; yes, in the case history.

I'll keep building toward the boring answers. The market will keep rewarding flashy agents until the first expensive promise. Both can be true at the same time.

---

### X-001
channel: x
audience: scene
pillar: builder
status: DRAFT
scheduled_for: week-1-mon

---

I'm Alena. Building Flywheel: inbound inquiry → booked job or accepted quote, on a script the business approved. The model rewrites. It does not decide. Shipping the build in public.

---

### X-002
channel: x
audience: both
pillar: cycle
status: DRAFT
scheduled_for: week-1-tue

---

"We'll get back to you" is not automation. It's a prettier voicemail. The cycle isn't closed until something is booked or quoted.

---

### X-003
channel: x
audience: scene
pillar: model
status: DRAFT
scheduled_for: week-1-wed

---

LLM extracts intent + drafts wording.
Router + qualification own the next state.
If your agent can invent a price, it isn't a cycle. It's a suggestion with side effects.

---

### X-004
channel: x
audience: both
pillar: cycle
status: DRAFT
scheduled_for: week-1-thu

---

Capture = name in an inbox.
Cycle = qualify, follow up, book.
Most SMB "AI" products sell the first word and charge as if they sold the second.

---

### X-005
channel: x
audience: scene
pillar: builder
status: DRAFT
scheduled_for: week-1-fri

---

Unfinished on purpose, posted on purpose: payment collection for the end customer is not connected yet. I'd rather timestamp that than hide it behind "full lead-to-cash."

---

### X-006
channel: x
audience: scene
pillar: builder
status: DRAFT
scheduled_for: week-2-mon

---

No industry `if` in the engine. If a non-legal business needs a code fork, the USP is fake. That's the test I'm running on camera this week.

---

### X-007
channel: x
audience: buyer
pillar: cycle
status: DRAFT
scheduled_for: week-2-wed

---

You already paid $600+ for some of those inquiries. If they die in voicemail, the ad account is not the leak. The cycle is.

---

### X-008
channel: x
audience: scene
pillar: model
status: DRAFT
scheduled_for: week-2-fri

---

Replay the same message id. You should not get a second booking. If you do, you don't have idempotency. You have a chatbot with a calendar plugin.

---

### X-009
channel: x
audience: both
pillar: cycle
status: DRAFT
scheduled_for: week-3-tue

---

Flywheel does not find you people. It does not drop the people who already wrote in. Different products. I will not blur that to sound bigger.

---

### X-010
channel: x
audience: scene
pillar: builder
status: DRAFT
scheduled_for: week-4-mon

---

US market. English. My face, my repo, my router. That's the trail. City comes after the trail, not before it.
