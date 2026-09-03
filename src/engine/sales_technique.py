"""Deterministic sales-technique layer.

The engine chooses WHICH move to make this turn. AI (when configured) only
changes HOW that move is worded. Techniques never change qualification
outcome, price, slot, discount, or whether a human is required -- the same
split as customer_tone (wording) vs QualificationService (decisions).

Zero-config: the playbook is universal, not authored per business. Owner-
written objection_responses still win on content; the technique only shapes
delivery of that already-approved text.
"""

from enum import StrEnum
import re
from typing import Mapping


class ObjectionCategory(StrEnum):
    PRICE = "price"
    TIMING = "timing"
    TRUST = "trust"
    COMPARISON = "comparison"
    FIT = "fit"
    CONSULT_SOMEONE_ELSE = "consult_someone_else"
    OTHER = "other"
    NONE = "none"


class SalesTechnique(StrEnum):
    DISCOVERY = "discovery"
    TRIAL_CLOSE = "trial_close"
    ACKNOWLEDGE_ISOLATE = "acknowledge_isolate"
    VALUE_REFRAME = "value_reframe"
    SOFT_PAUSE = "soft_pause"
    PROCESS_PROOF = "process_proof"
    FIT_DIAGNOSTIC = "fit_diagnostic"
    CHAMPION = "champion"
    COMPARISON_BRIDGE = "comparison_bridge"
    SUMMARY_NEXT_STEP = "summary_next_step"
    ALTERNATIVE_CLOSE = "alternative_close"
    COMMITMENT_CLOSE = "commitment_close"
    NURTURE = "nurture"
    BREAKUP = "breakup"


class ConversationKind(StrEnum):
    QUALIFYING_QUESTION = "qualifying_question"
    OBJECTION = "objection"
    COMMERCIAL_OFFER = "commercial_offer"
    FOLLOW_UP = "follow_up"


# Shared across every wording prompt. Identical text everywhere, so the
# technique behaves the same regardless of which generator is speaking --
# the only thing that varies per prompt is WHAT is being said.
SALES_TECHNIQUE_INSTRUCTION = (
    "\nBUSINESS_CONTEXT.sales_technique is the approved sales move for THIS turn, "
    "chosen by the engine -- apply it to the FORM of the wording, never to the facts, "
    "questions, prices, promises, or next step. discovery: ask only the allowed "
    "questions as a consultant matching them to the right next step; do not add "
    "questions. trial_close: frame the remaining allowed question as the last detail "
    "before the already-authorized next step; do not invent what that step costs. "
    "value_reframe: acknowledge a cost concern, then ground only in BUSINESS_CONTEXT "
    "facts (a quote or booking is not a charge); never a discount, price, or "
    "guarantee. soft_pause: give permission to go slowly; keep the next allowed "
    "question small. process_proof: point only at the real process in "
    "BUSINESS_CONTEXT (a person reviews, a quote comes first, booking is just a "
    "time). fit_diagnostic: treat remaining allowed questions as how fit is checked; "
    "do not claim the service is or is not a fit. champion: make the next allowed "
    "step easy to share with someone else; no new offers. comparison_bridge: do not "
    "name competitors or claim to be cheaper or better; return to this business's "
    "actual process. acknowledge_isolate: name the concern in your own words, then "
    "continue the allowed next step; do not argue. summary_next_step: recap only "
    "facts already in BUSINESS_CONTEXT, then the approved next step. "
    "alternative_close: present the given options as a choice between them; do not "
    "add options. commitment_close: ask for a clear yes/no on the already-presented "
    "offer; do not sweeten it. nurture: a short, non-urgent check-in plus any "
    "still-outstanding allowed question. breakup: a clean last check-in that lets "
    "them close it out; not guilt, not a new offer. This changes phrasing and "
    "structure only."
)


_PRICE = re.compile(
    r"\b(?:expensive|too much|afford|cheaper|cheap|budget|price|cost|pricing|"
    r"how much|spend|spending|rate|fee|fees)\b",
    re.IGNORECASE,
)
_TIMING = re.compile(
    r"\b(?:think about it|not ready|maybe later|not now|need (?:some )?time|"
    r"call(?:\s+me)? back|get back to you|later on|next (?:week|month)|"
    r"hold off|not sure (?:yet|right now))\b",
    re.IGNORECASE,
)
_TRUST = re.compile(
    r"\b(?:scam|legit(?:imate)?|trust|reviews?|qualified|licensed|experienced|"
    r"how do i know|are you real|is this real)\b",
    re.IGNORECASE,
)
_COMPARISON = re.compile(
    r"\b(?:other (?:options?|companies|places)|somewhere else|someone else|"
    r"competitor|shopping around|comparing|another (?:company|place|quote)|"
    r"got a quote)\b",
    re.IGNORECASE,
)
_FIT = re.compile(
    r"\b(?:(?:not sure|unsure) (?:this|it) (?:is )?(?:for me|a fit|the right fit)|"
    r"right fit|my situation|will this (?:even )?work|does this work|"
    r"apply to me|too (?:big|small) for)\b",
    re.IGNORECASE,
)
_CONSULT = re.compile(
    r"\b(?:talk to my|ask my|check with|run (?:it|this) by|tell my|"
    r"(?:husband|wife|spouse|partner|boss|manager|parents?|mom|dad|kids?) "
    r"(?:first|about)|consult (?:my|with))\b",
    re.IGNORECASE,
)

_OBJECTION_TECHNIQUE = {
    ObjectionCategory.PRICE: SalesTechnique.VALUE_REFRAME,
    ObjectionCategory.TIMING: SalesTechnique.SOFT_PAUSE,
    ObjectionCategory.TRUST: SalesTechnique.PROCESS_PROOF,
    ObjectionCategory.COMPARISON: SalesTechnique.COMPARISON_BRIDGE,
    ObjectionCategory.FIT: SalesTechnique.FIT_DIAGNOSTIC,
    ObjectionCategory.CONSULT_SOMEONE_ELSE: SalesTechnique.CHAMPION,
    ObjectionCategory.OTHER: SalesTechnique.ACKNOWLEDGE_ISOLATE,
}

_OBJECTION_ACKNOWLEDGMENTS = {
    SalesTechnique.VALUE_REFRAME: "Cost is a fair thing to settle before going further.",
    SalesTechnique.SOFT_PAUSE: "No rush -- we can take this one step at a time.",
    SalesTechnique.PROCESS_PROOF: "It's reasonable to want to know how this actually works.",
    SalesTechnique.FIT_DIAGNOSTIC: "Let's check whether this is the right fit before anything else.",
    SalesTechnique.CHAMPION: "Totally fine to run this by someone else first.",
    SalesTechnique.COMPARISON_BRIDGE: "It's smart to compare how this would actually work.",
    SalesTechnique.ACKNOWLEDGE_ISOLATE: "That's a completely fair thing to want to be sure about.",
}


def classify_objection_category(phrase: str | None) -> ObjectionCategory:
    """Closed keyword classifier for an already-detected objection phrase.

    Does not decide whether something IS an objection -- IntentResult.objection_phrase
    already did that. This only picks which objection move to use. First matching
    category wins, in an order that prefers the more specific sales situations
    (consult / comparison / fit / trust / timing) over the broader price lexicon.
    """
    if not phrase or not phrase.strip():
        return ObjectionCategory.NONE
    text = phrase.strip()
    if _CONSULT.search(text):
        return ObjectionCategory.CONSULT_SOMEONE_ELSE
    if _COMPARISON.search(text):
        return ObjectionCategory.COMPARISON
    if _FIT.search(text):
        return ObjectionCategory.FIT
    if _TRUST.search(text):
        return ObjectionCategory.TRUST
    if _TIMING.search(text):
        return ObjectionCategory.TIMING
    if _PRICE.search(text):
        return ObjectionCategory.PRICE
    return ObjectionCategory.OTHER


def select_sales_technique(
    *,
    kind: ConversationKind | str,
    missing_item_count: int = 0,
    already_qualifying: bool = False,
    objection_phrase: str | None = None,
    objection_category: ObjectionCategory | None = None,
    slot_count: int = 0,
    commercial_mode: str | None = None,
    follow_up_attempt: int | None = None,
    follow_up_maximum_attempts: int | None = None,
) -> SalesTechnique:
    """Pure selector -- no I/O, no AI, no Business DNA branching."""
    resolved_kind = ConversationKind(kind)
    if resolved_kind is ConversationKind.OBJECTION:
        category = objection_category or classify_objection_category(objection_phrase)
        return _OBJECTION_TECHNIQUE.get(category, SalesTechnique.ACKNOWLEDGE_ISOLATE)
    if resolved_kind is ConversationKind.QUALIFYING_QUESTION:
        if already_qualifying and missing_item_count == 1:
            return SalesTechnique.TRIAL_CLOSE
        return SalesTechnique.DISCOVERY
    if resolved_kind is ConversationKind.FOLLOW_UP:
        if (
            follow_up_attempt is not None
            and follow_up_maximum_attempts is not None
            and follow_up_attempt >= follow_up_maximum_attempts
        ):
            return SalesTechnique.BREAKUP
        return SalesTechnique.NURTURE
    if resolved_kind is ConversationKind.COMMERCIAL_OFFER:
        mode = commercial_mode or ""
        if mode in {"awaiting_slot", "awaiting_reschedule_slot"} or slot_count:
            if slot_count > 1:
                return SalesTechnique.ALTERNATIVE_CLOSE
            return SalesTechnique.SUMMARY_NEXT_STEP
        if mode == "quote_presented":
            return SalesTechnique.COMMITMENT_CLOSE
        if mode == "awaiting_pricing_input":
            return SalesTechnique.DISCOVERY
        return SalesTechnique.SUMMARY_NEXT_STEP
    raise ValueError(f"unsupported conversation kind: {kind}")


def frame_with_technique(
    technique: SalesTechnique,
    body: str,
    *,
    fact: str | None = None,
) -> str:
    """Deterministic wording wrap. Discovery is identity so configured
    questions stay exactly as the owner wrote them. Other techniques add a
    closed, fact-free frame; optional `fact` is a structural Business DNA
    sentence already computed by the caller (never a price)."""
    body = body.strip()
    extra = fact.strip() if isinstance(fact, str) and fact.strip() else None
    if technique is SalesTechnique.DISCOVERY:
        return body
    if technique is SalesTechnique.TRIAL_CLOSE:
        return f"One last detail and we can move forward. {body}"
    if technique is SalesTechnique.NURTURE:
        return body
    if technique is SalesTechnique.BREAKUP:
        if body:
            return (
                "I'll close this out on my side unless you'd still like help. "
                f"{body}"
            )
        return "I'll close this out on my side unless you'd still like help."
    if technique is SalesTechnique.ALTERNATIVE_CLOSE:
        return body
    if technique is SalesTechnique.COMMITMENT_CLOSE:
        return body
    if technique is SalesTechnique.SUMMARY_NEXT_STEP:
        return body
    acknowledgment = _OBJECTION_ACKNOWLEDGMENTS.get(technique)
    if acknowledgment is None:
        return body
    if extra:
        return f"{acknowledgment} {extra}"
    return acknowledgment


def objection_technique_for(phrase: str | None) -> tuple[ObjectionCategory, SalesTechnique]:
    category = classify_objection_category(phrase)
    technique = _OBJECTION_TECHNIQUE.get(category, SalesTechnique.ACKNOWLEDGE_ISOLATE)
    return category, technique


def technique_context(technique: SalesTechnique) -> Mapping[str, str]:
    return {"sales_technique": technique.value}


def slot_lead_in(*, reschedule: bool, slot_count: int) -> str:
    """Alternative close when there is a real choice; otherwise a single
    next-step prompt. Facts (the numbered times) stay in the caller."""
    technique = select_sales_technique(
        kind=ConversationKind.COMMERCIAL_OFFER,
        slot_count=slot_count,
        commercial_mode="awaiting_reschedule_slot" if reschedule else "awaiting_slot",
    )
    if technique is SalesTechnique.ALTERNATIVE_CLOSE:
        if reschedule:
            return "Which of these new times works better for you:"
        return "Which of these times works better for you:"
    if reschedule:
        return "Here's a new time that works:"
    return "Here's a time that works:"


def quote_accept_prompt() -> str:
    """Commitment close on an already-calculated quote -- asks for yes/no
    without adding a discount, guarantee, or extra offer."""
    return "If this looks right, reply accept or decline."
