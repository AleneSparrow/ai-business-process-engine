# Candidate sales knowledge cards — 2026-09-04

**Status:** candidate / unapproved. Nothing here is published, referenced by any
prompt, or used by `SalesPolicyEngine`. Part A of
`docs/agent-prompts/claude-code-sales-knowledge-and-evals.md`.

## Provenance caveat — read before using any of this

The task template for Part A ("Проанализируй только предоставленные
источники") assumes the owner hands over specific source documents so every
principle can carry an exact, page-verified citation. No source documents were
provided in this session. Per the owner's explicit instruction to proceed
anyway, this document draws on well-established, widely-cited, publicly
documented sales methodologies and consumer-psychology research instead of an
owner-supplied text.

This is a materially weaker provenance guarantee than the process in
`docs/sales-agent-implementation-plan-ru.md` section 8 describes, and it must
not be treated as equivalent:

- **Title, author, and core concept** for each card are stated from reliable
  general knowledge and are very unlikely to be wrong.
- **Exact page/section location** is *not* verified against a purchased or
  physical copy in this session. Where a specific location is given below, it
  is a best-effort reference (e.g. "the price-objection chapter"), not a
  page-checked citation, and must be confirmed against an actual copy before
  any card is approved.
- No long passage from any source is reproduced here — every `principle` and
  `approved_example` below is my own short paraphrase/derived rule, per the
  copyright and "no fabricated exact citations" constraints on this task.
- Applicability to *this specific product* (a US self-serve SaaS, chat-based,
  lead-to-deal flow, Starter $199/Pro $499, 7-day trial, zero-config across
  verticals) is flagged per card — several of these frameworks were written
  for higher-touch B2B or enterprise negotiation contexts and their fit here
  is a judgment call for the owner, not a settled fact.

Every card below is `status: "candidate"`, `version: 0`. None should be
treated as approved, referenced by `sales_playbook`, or used to answer a real
customer.

## Contradictions between sources (reported, not resolved)

1. **Validate-then-redirect vs. constructive disagreement.** The classic
   "acknowledge → feel/felt/found → redirect" objection script (card 09)
   assumes the safest posture is always to agree with the customer's frame
   first. *The Challenger Sale* (card 02) argues the opposite for considered
   B2B purchases: a rep who only validates the customer's existing view
   never reframes it toward a need the business is actually positioned to
   solve, and deliberately introduces "constructive tension" instead.
   Unresolved — the two do not compose cleanly, and picking one changes the
   tone of every objection-handling knowledge card downstream.
2. **Scarcity/urgency framing vs. the product's own no-fabrication rule.**
   Cialdini's scarcity principle (card 03e) is one of the most cited levers in
   consumer sales psychology, but it only works ethically when the scarcity
   is real (an actual limited slot count, an actual deadline). This product's
   hard constraint — AI may never state a business fact it cannot verify —
   means this card is usable only when Business DNA already contains a real,
   verifiable scarcity fact (e.g. actual remaining slots this week); it must
   never be used to manufacture pressure. Flagged as **conditionally
   prohibited by default**, not a straightforward "approved" card.
3. **High-stakes negotiation techniques vs. a low-ticket, first-contact,
   self-serve product.** *Never Split the Difference* (card 04) was written
   for hostage negotiation and later high-value B2B deals with multiple
   sessions and real walk-away power. This product's typical interaction is a
   lower-stakes, faster, often first-message chat. Techniques like calibrated
   "how"/"what" questions likely transfer; techniques assuming a long
   back-and-forth or real leverage on either side likely do not, and applying
   them uncritically risks sounding manipulative in a five-minute chat. Owner
   review needed per-card, not as a blanket import.
4. **General SaaS trial-conversion research (card 07) is industry-level, not
   book-level.** Unlike the others, this card is not attributable to one
   named source — it reflects commonly repeated findings across SaaS-industry
   analyses (time-to-first-value, onboarding friction) rather than a single
   citable text. It is included because it is directly relevant to this
   product's own trial model, but it carries the lowest provenance confidence
   of anything here and should be the first candidate the owner either
   grounds in a specific named source or drops.

## Candidate cards

```json
[
  {
    "knowledge_id": "candidate-discovery-spin-001",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "SPIN Selling",
      "author": "Neil Rackham",
      "concept": "Situation / Problem / Implication / Need-payoff question sequence",
      "provenance_confidence": "title/author/concept: high; exact page: not verified this session"
    },
    "principle": "Move discovery questions through four types in order: fact-finding (situation), problem-finding, then questions that surface the cost of NOT solving the problem (implication), then questions that get the customer to state the value of solving it themselves (need-payoff) -- rather than pitching value before the customer has said it in their own words.",
    "applicable_when": ["stage == DISCOVERY", "customer_problem or desired_outcome is missing"],
    "prohibited_when": ["customer has already stated both problem and desired outcome -- re-asking is redundant, not thorough"],
    "required_sequence": ["ask_situation_or_problem_question", "if_problem_confirmed_ask_implication_question", "let_customer_state_the_payoff_before_presenting_value"],
    "forbidden_actions": ["stating the value proposition before the customer has confirmed a problem", "asking more than one discovery question per message (matches ASK_DISCOVERY_QUESTION's existing max_questions_per_message constraint in the sales_playbook draft)"],
    "approved_examples": [
      "What does your current follow-up process look like day to day?",
      "If a lead doesn't get a reply for a few hours, what tends to happen to it?"
    ],
    "fit_for_this_product": "high -- this is close to a 1:1 match for the existing DISCOVERY stage and ASK_DISCOVERY_QUESTION move."
  },
  {
    "knowledge_id": "candidate-presentation-challenger-teaching-002",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "The Challenger Sale",
      "author": "Matthew Dixon and Brent Adamson",
      "concept": "Commercial teaching / reframing the customer's own understanding of their problem",
      "provenance_confidence": "title/author/concept: high; exact page: not verified this session"
    },
    "principle": "For a customer who has not yet recognized the full cost of their problem, briefly reframe it using a fact or comparison they had not considered, before presenting the offer -- rather than only mirroring back what they already believe.",
    "applicable_when": ["stage == PRESENTATION", "customer_problem is stated but understates its own cost or urgency"],
    "prohibited_when": ["no approved business_fact or knowledge-backed comparison is available to reframe with -- do not invent a statistic or comparison"],
    "required_sequence": ["confirm_the_customers_stated_problem", "add_one_verifiable_fact_that_reframes_its_cost", "connect_to_the_relevant_service"],
    "forbidden_actions": ["citing a statistic, benchmark, or comparison not present in Business DNA or an approved knowledge card", "arguing with the customer's stated experience"],
    "approved_examples": [
      "Missed leads are the ones we can put a number on, but the ones handled without a script are what tend to actually pay for the follow-up work later."
    ],
    "fit_for_this_product": "medium -- promising for PRESENT_RELEVANT_VALUE, but every reframe must cite only approved Business DNA facts; contradiction 1 above applies here directly."
  },
  {
    "knowledge_id": "candidate-objection-price-cialdini-reciprocity-003a",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "Influence: The Psychology of Persuasion",
      "author": "Robert Cialdini",
      "concept": "Reciprocity",
      "provenance_confidence": "title/author/concept: high; exact page: not verified this session"
    },
    "principle": "A small, genuine, unconditional concession or piece of free value offered before asking for commitment increases the odds of a later yes -- but the concession must be real and already authorized (e.g. a free consultation slot that is actually in Business DNA), never invented on the spot.",
    "applicable_when": ["Business DNA already defines a free/no-cost offer (e.g. a free consultation)"],
    "prohibited_when": ["no such offer exists in Business DNA -- never invent a free add-on, waived fee, or discount to create reciprocity"],
    "required_sequence": ["state_the_existing_free_offer_plainly", "do_not_frame_it_as_conditional_on_an_immediate_yes"],
    "forbidden_actions": ["inventing a concession", "implying the free offer expires unless it actually does per Business DNA"],
    "approved_examples": ["The first consultation is free either way -- happy to set that up regardless of what you decide after."],
    "fit_for_this_product": "medium -- only usable where Business DNA already authorizes a real free offer; otherwise not applicable, per this product's no-fabrication rule."
  },
  {
    "knowledge_id": "candidate-objection-price-cialdini-consistency-003b",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "Influence: The Psychology of Persuasion",
      "author": "Robert Cialdini",
      "concept": "Commitment and consistency (small-yes ladder)",
      "provenance_confidence": "title/author/concept: high; exact page: not verified this session"
    },
    "principle": "A person is more likely to agree to a larger request after already agreeing, out loud, to a small, related one. Build commitment through a short sequence of small confirmations (problem confirmed -> interest confirmed -> next step selected) rather than asking for the full commitment in one step.",
    "applicable_when": ["stage in {NEEDS_CONFIRMED, PRESENTATION, COMMITMENT}"],
    "prohibited_when": ["the customer has already given an unhedged yes -- do not manufacture extra small-yes steps once real commitment is already stated, that reads as stalling"],
    "required_sequence": ["confirm_problem", "confirm_interest", "offer_one_next_step"],
    "forbidden_actions": ["asking a throwaway yes/no question with no bearing on the actual decision, purely to manufacture a 'yes' -- must be substantively true each time"],
    "approved_examples": ["So the main thing is getting to leads faster -- did I get that right?"],
    "fit_for_this_product": "high -- this is already the shape of the commitment_ladder field in the draft sales_playbook (section 9 of the implementation plan); this card just names why it works."
  },
  {
    "knowledge_id": "candidate-general-cialdini-scarcity-003e",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "Influence: The Psychology of Persuasion",
      "author": "Robert Cialdini",
      "concept": "Scarcity",
      "provenance_confidence": "title/author/concept: high; exact page: not verified this session"
    },
    "principle": "People weigh a limited opportunity more heavily than an equally good but open-ended one. Only applies when the limit is real and verifiable (e.g. an actual remaining slot count for this week from Business DNA/availability data).",
    "applicable_when": ["Business DNA or live availability data provides a real, current, verifiable scarcity fact"],
    "prohibited_when": ["no verifiable scarcity fact exists -- this is the single highest-risk card in this set for turning into a fabricated-urgency violation; see Contradiction 2 above"],
    "required_sequence": ["state_only_the_verified_fact", "no_added_pressure_language"],
    "forbidden_actions": ["inventing or exaggerating a deadline, slot count, or limited-time framing", "using vague urgency language ('spots are filling up') without a specific verified number"],
    "approved_examples": ["There are two consultation slots left this week if either of those work for you."],
    "fit_for_this_product": "low by default -- recommend the owner mark this card 'prohibited' rather than 'approved' unless a real availability feed is wired to back it, given how easily it slides into an unsupported claim."
  },
  {
    "knowledge_id": "candidate-objection-diagnostic-question-voss-004",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "Never Split the Difference",
      "author": "Chris Voss and Tahl Raz",
      "concept": "Calibrated open questions and labeling",
      "provenance_confidence": "title/author/concept: high; exact page: not verified this session"
    },
    "principle": "Instead of asking a closed yes/no diagnostic question ('is it the price?'), use an open 'what' or 'how' question that lets the customer name the real cause themselves, and reflect their concern back in your own words before responding ('it sounds like the concern is...') to confirm you understood before answering.",
    "applicable_when": ["objection.status == ACTIVE and objection.cause is missing"],
    "prohibited_when": ["objection.cause is already known -- do not re-diagnose an already-diagnosed objection"],
    "required_sequence": ["label_the_concern_in_your_own_words", "ask_one_open_diagnostic_question", "wait_for_the_answer_before_answering"],
    "forbidden_actions": ["asking more than one diagnostic question per message", "answering the objection before the cause is confirmed"],
    "approved_examples": ["It sounds like the price is the sticking point -- is that more about the total budget, or whether it'll actually pay off?"],
    "fit_for_this_product": "high for the question mechanic itself; see Contradiction 3 for the broader technique's fit in a short, first-contact chat."
  },
  {
    "knowledge_id": "candidate-followup-cadence-multitouch-005",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "Fanatical Prospecting",
      "author": "Jeb Blount",
      "concept": "Multi-touch, multi-channel follow-up cadence",
      "provenance_confidence": "title/author/concept: high; exact page: not verified this session"
    },
    "principle": "A single follow-up attempt materially undersells response rates compared to a short sequence of attempts spaced over days, and varying the channel (e.g. SMS then a different-toned message) outperforms repeating the identical message.",
    "applicable_when": ["follow_up_reason in {UNANSWERED_DISCOVERY, QUOTE_PENDING, BOOKING_NOT_COMPLETED, DORMANT_INTEREST}"],
    "prohibited_when": ["consent, STOP, or quiet hours would be violated by the next attempt -- those constraints are absolute and outrank this card"],
    "required_sequence": ["vary_the_opening_line_each_attempt", "reference_the_specific_prior_context_not_a_generic_nudge"],
    "forbidden_actions": ["sending the identical message text twice", "increasing pressure/urgency language on later attempts"],
    "approved_examples": ["Following up on the missed-leads conversation from earlier this week -- still a good time to look at options?"],
    "fit_for_this_product": "high -- matches the existing follow_up cadence_hours/maximum_attempts fields already drafted in section 9."
  },
  {
    "knowledge_id": "candidate-price-framing-loss-aversion-006",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "Prospect Theory: An Analysis of Decision under Risk (and its popular treatment in behavioral-economics writing since)",
      "author": "Daniel Kahneman and Amos Tversky",
      "concept": "Loss aversion / framing effect",
      "provenance_confidence": "concept: high, very widely replicated; this specific paper's page location: not verified this session -- treat as a research finding, not a sales book"
    },
    "principle": "The same fact framed as an avoidable ongoing loss (what missed leads already cost) is generally weighed more heavily by a decision-maker than the identical fact framed as a potential future gain. Only usable with a real, already-known customer fact -- never an invented cost estimate.",
    "applicable_when": ["the customer has already stated a concrete current problem with a describable cost (e.g. missed leads, no-shows)"],
    "prohibited_when": ["no concrete customer-stated fact exists to frame -- do not invent a dollar figure or percentage"],
    "required_sequence": ["restate_the_customers_own_stated_problem_as_an_ongoing_cost"],
    "forbidden_actions": ["stating a specific dollar amount or percentage the customer did not provide and Business DNA does not confirm"],
    "approved_examples": ["Every missed follow-up right now is a lead who found somebody else -- that's the part this would close."],
    "fit_for_this_product": "medium -- powerful but easy to misuse into an unsupported claim; keep to reframing the customer's own stated fact, never a manufactured number."
  },
  {
    "knowledge_id": "candidate-trial-time-to-value-007",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "General SaaS self-serve trial-conversion industry findings",
      "author": "various (industry analyses, e.g. OpenView/ProfitWell-style benchmarking commonly cited in SaaS operator writing)",
      "concept": "Time-to-first-value predicts trial-to-paid conversion",
      "provenance_confidence": "LOW -- not a single citable book; this is the weakest-provenance card in this set (see contradiction 4). Recommend the owner either name a specific source to replace this or drop it."
    },
    "principle": "A trial user who experiences a concrete, specific result early is materially more likely to convert than one who is still exploring generic features when the trial period is half over -- so a sales conversation with a trial customer should aim to identify and confirm one concrete outcome fast, rather than a broad feature tour.",
    "applicable_when": ["customer is in an active free trial (7-day trial per this product's own model) and stage in {PRESENTATION, COMMITMENT}"],
    "prohibited_when": ["no trial-status signal is actually known -- do not assume trial status"],
    "required_sequence": ["identify_the_one_outcome_that_matters_most_to_this_customer", "confirm_it_can_be_demonstrated_within_the_trial_window"],
    "forbidden_actions": ["promising a specific quantified outcome ('you'll book 3x more calls') that is not an approved business fact"],
    "approved_examples": ["Given the trial's a week, the fastest win is probably getting your intake flow live first -- want to start there?"],
    "fit_for_this_product": "directly relevant to this product's own trial model, but lowest-confidence provenance here -- treat as a placeholder pending a real source."
  },
  {
    "knowledge_id": "candidate-objection-script-feel-felt-found-CONTESTED-008",
    "version": 0,
    "status": "candidate",
    "source": {
      "title": "Feel-Felt-Found (widely attributed to classic mid-20th-century sales training, commonly associated with Zig Ziglar-era material)",
      "author": "attribution uncertain -- this phrase circulates broadly without a single clearly-original source",
      "concept": "Acknowledge -> relate -> redirect objection script",
      "provenance_confidence": "LOW -- attribution itself is disputed; included only because it is extremely widely taught, not because its source is solid"
    },
    "principle": "Acknowledge the objection ('I understand how you feel'), relate it to a past similar case ('others have felt the same way'), then redirect to a resolution ('what they found was...'). Widely taught but also widely criticized by modern sales trainers (including Voss- and Challenger-style writing, see Contradiction 1) as sounding scripted and reducing trust when used verbatim.",
    "applicable_when": ["explicitly marked CONTESTED -- not recommended for direct approval as-is"],
    "prohibited_when": ["always, in this exact scripted three-beat form -- recommend the owner either reject this card outright or approve only a paraphrased, non-formulaic version"],
    "required_sequence": [],
    "forbidden_actions": ["using the exact 'feel / felt / found' phrasing verbatim -- it is recognizable enough that customers may notice the script"],
    "approved_examples": [],
    "fit_for_this_product": "low -- flagged for the owner to explicitly reject or substantially rewrite rather than approve; included only to surface the contradiction with card 02/04, per the task's instruction to report contradictions rather than resolve them."
  }
]
```

## What the owner needs to do with this

Per the plan's own process (section 8, step 3: "Ни одна карточка не публикуется
автоматически"), none of this is usable as-is. Concretely:

1. Decide the posture question in Contradiction 1 (validate-first vs.
   constructive reframe) -- it changes several cards at once.
2. Either reject `candidate-general-cialdini-scarcity-003e` outright or wire a
   real availability feed before ever approving it.
3. Either name a real source for
   `candidate-trial-time-to-value-007` or drop it -- it is the weakest card
   here.
4. Explicitly reject or rewrite
   `candidate-objection-script-feel-felt-found-CONTESTED-008`.
5. For every remaining card, confirm the underlying book/paper against an
   actual copy before treating the citation as production-grade provenance --
   this session did not do that verification.
