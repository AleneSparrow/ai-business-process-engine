"""Deterministic sales next-step. The AI never chooses this.

Product contract (owner, 2026-09-04):

- Closed cycle from inbound inquiry to a deal. This is a full replacement for
  the person who sits and processes leads — not a CRM that captures a name
  and waits.
- Objection handling, tone adaptation, and sales technique are encoded here
  as rules. AI may rephrase approved copy; it may not pick the move, the
  price, or whether to escalate.
- Lead generation is a later, separate product. This module never promises
  it, and never treats an inbound inquiry as a "cold lead".
- Flywheel must sell itself with this same engine: a visitor who asks about
  Flywheel is a lead, and the cycle must close on a demo or trial time.

Without a price (which the engine must never invent) the universal close is
a scheduled next step — consult, visit, demo, or call. That is an advance,
not a handoff. Human review stays for safety, out-of-policy requests, and
an owner who explicitly opts a service back to handoff in Settings.
"""

from dataclasses import dataclass
from enum import StrEnum

from src.domain.qualification import CustomerTone
from src.domain.states import ProcessState

DEAL_STATES = frozenset({
    ProcessState.BOOKED,
    ProcessState.WON,
    ProcessState.PAID,
    ProcessState.COMPLETED,
})


class SalesMove(StrEnum):
    DISCOVER = "discover"
    OFFER_COMMITMENT = "offer_commitment"
    HANDLE_OBJECTION = "handle_objection"
    TRIAL_CLOSE = "trial_close"
    NURTURE = "nurture"
    ESCALATE_SAFETY = "escalate_safety"
    DEAL_DONE = "deal_done"


class ObjectionKind(StrEnum):
    PRICE = "price"
    TIMING = "timing"
    TRUST = "trust"
    COMPARISON = "comparison"
    FIT = "fit"
    CONSULT_SOMEONE_ELSE = "consult_someone_else"
    OTHER = "other"


# After an objection: acknowledge (elsewhere), then ask for a commitment.
CLOSE_ASK_SLOT = (
    "If that works, I can hold a time — reply with 1, 2, or 3 when I share "
    "the options, or tell me a window that fits."
)
CLOSE_ASK_QUOTE = (
    "If that works, reply accept to go ahead with the quote, or tell me "
    "what you'd like to change."
)
CLOSE_ASK_TIMING = (
    "I can hold a time so this doesn't slip — reply 1, 2, or 3 when I share "
    "the options, or name a window that fits."
)
CLOSE_ASK_THIRD_PARTY = (
    "I can hold a time you can share with them — reply 1, 2, or 3 when I "
    "share the options."
)

NURTURE_SLOT = (
    "I can still hold a time for you — reply 1, 2, or 3, or tell me a better window."
)
NURTURE_QUOTE = (
    "Your quote is still available. Reply accept to go ahead, or tell me "
    "what you'd like to change."
)
NURTURE_DISCOVERY = (
    "Whenever you are ready I can take the next detail and hold a time."
)

_PRICE_CUES = ("expensive", "too much", "cost", "price", "afford", "budget", "cheap")
_TIMING_CUES = ("think about", "not ready", "later", "not now", "maybe later", "need time")
_TRUST_CUES = ("does this work", "scam", "legit", "not sure you", "can you actually")
_COMPARE_CUES = ("other option", "competitor", "someone else quoted", "shopping around")
_FIT_CUES = ("not for me", "not sure this fits", "wrong service", "do you even")
_THIRD_PARTY_CUES = (
    "ask my", "talk to my", "check with", "husband", "wife", "partner", "boss", "spouse",
)


@dataclass(frozen=True, slots=True)
class DialogueSnapshot:
    """Facts already on the case — never model-invented."""

    state: ProcessState
    missing_complete: bool
    has_objection: bool
    commercial_mode: str | None
    requires_human: bool
    customer_tone: CustomerTone | None = None
    inbound_turns: int = 0


def classify_objection(phrase: str | None) -> ObjectionKind:
    """Keyword analysis of the customer's own words. Not an LLM judgment."""
    if not phrase or not phrase.strip():
        return ObjectionKind.OTHER
    text = phrase.casefold()
    checks = (
        (ObjectionKind.PRICE, _PRICE_CUES),
        (ObjectionKind.TIMING, _TIMING_CUES),
        (ObjectionKind.CONSULT_SOMEONE_ELSE, _THIRD_PARTY_CUES),
        (ObjectionKind.COMPARISON, _COMPARE_CUES),
        (ObjectionKind.TRUST, _TRUST_CUES),
        (ObjectionKind.FIT, _FIT_CUES),
    )
    for kind, cues in checks:
        if any(cue in text for cue in cues):
            return kind
    return ObjectionKind.OTHER


def close_ask_for_fulfillment(fulfillment_type: str | None) -> str:
    if fulfillment_type == "quote_required":
        return CLOSE_ASK_QUOTE
    return CLOSE_ASK_SLOT


def close_ask_for_objection(kind: ObjectionKind, fulfillment_type: str | None) -> str:
    """Technique: feel-felt-found is the acknowledgment; this is the close.

    Timing and third-party objections get a hold-the-slot ask. Price on a
    quote path asks for accept. Everything else uses the universal next-step
    close. Tone never changes the move — only later wording adapters may
    shorten or warm the same ask.
    """
    if kind is ObjectionKind.TIMING:
        return CLOSE_ASK_TIMING
    if kind is ObjectionKind.CONSULT_SOMEONE_ELSE:
        return CLOSE_ASK_THIRD_PARTY
    return close_ask_for_fulfillment(fulfillment_type)


def append_close_ask(
    message: str,
    objection_phrase: str | None,
    fulfillment_type: str | None,
) -> str:
    """Acknowledgment (AI or deterministic) plus the engine-chosen close.

    The model must not invent this ask. If the acknowledgment already contains
    the approved close, do not duplicate it.
    """
    ask = close_ask_for_objection(classify_objection(objection_phrase), fulfillment_type)
    text = (message or "").strip()
    if not text:
        return ask
    if ask.casefold() in text.casefold():
        return text
    return f"{text} {ask}"


def nurture_copy(state: ProcessState, *, missing_complete: bool) -> str:
    """Approved follow-up wording for a stalled case. Never invents a price."""
    if state is ProcessState.QUOTED:
        return NURTURE_QUOTE
    if state is ProcessState.QUALIFIED:
        return NURTURE_SLOT
    if missing_complete:
        return NURTURE_DISCOVERY
    return ""


def next_move(snapshot: DialogueSnapshot) -> SalesMove:
    """Pick the sales move from case facts. AI does not call this to decide
    policy — the engine does, then asks AI only to phrase approved copy."""
    if snapshot.requires_human:
        return SalesMove.ESCALATE_SAFETY
    if snapshot.state in DEAL_STATES:
        return SalesMove.DEAL_DONE
    if snapshot.has_objection:
        return SalesMove.HANDLE_OBJECTION
    if not snapshot.missing_complete:
        return SalesMove.DISCOVER
    if snapshot.state is ProcessState.QUOTED:
        return SalesMove.TRIAL_CLOSE
    if snapshot.state is ProcessState.QUALIFIED and snapshot.commercial_mode in {
        "awaiting_slot",
        "awaiting_reschedule_slot",
    }:
        return SalesMove.TRIAL_CLOSE
    if snapshot.state is ProcessState.QUALIFIED:
        return SalesMove.OFFER_COMMITMENT
    if snapshot.inbound_turns > 0 and snapshot.state in {
        ProcessState.NEW_LEAD,
        ProcessState.CONTACTED,
        ProcessState.QUALIFYING,
        ProcessState.QUALIFIED,
        ProcessState.QUOTED,
    }:
        return SalesMove.NURTURE
    return SalesMove.DISCOVER
