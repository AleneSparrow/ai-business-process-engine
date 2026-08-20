"""Objection-reassurance wording boundary.

Kept as its own generator (mirroring QuestionGenerator / CustomerResponseGenerator)
rather than folded into either: it answers a different question ("does the customer's
doubt map to something the owner already approved wording for?") than either of those
do, and the AI-backed implementation's job is narrowly to *select and rephrase* one
owner-approved entry, never to draft new reassurance content of its own -- the same
never-invents guarantee the rest of the engine already relies on.

Two generators live here, for two different situations (see
LeadIntakeService._with_reassurance for how they're chosen):

- ReassuranceResponseGenerator / Deterministic-/AI- implementations: the owner has
  authored qualification.objection_responses entries -- select and rephrase one,
  verbatim-grounded, never invent.
- UniversalReassuranceResponseGenerator / Deterministic-/AI- implementations: the
  owner has NOT configured anything (confirmed live, 2026-08-19: this is every
  business by default, since objection_responses is optional and nothing prompts an
  owner to fill it in) -- ground the reassurance in the business's own already-
  collected facts (service description, fulfillment type, booking availability)
  instead of requiring manual setup. This is what makes objection handling work
  "out of the box" the way Alena described it: the business doesn't write the
  playbook, we do.
"""

from hashlib import sha256
from typing import Mapping, Protocol, Sequence

from src.domain.qualification import CustomerResponse, CustomerTone


class ReassuranceResponseGenerator(Protocol):
    def generate(
        self,
        objection_phrase: str,
        approved_responses: Sequence[Mapping[str, object]],
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse: ...


class DeterministicReassuranceResponseGenerator:
    """Test/local fallback: no semantic matching, just the first configured
    entry's approved wording verbatim. The real product path is the
    AI-backed generator (src/ai/adapters.py), which actually selects the
    relevant entry and adapts its tone. customer_tone is accepted for
    protocol compatibility but unused here -- no AI call, nothing to adapt."""

    def generate(
        self,
        objection_phrase: str,
        approved_responses: Sequence[Mapping[str, object]],
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse:
        if not approved_responses:
            raise ValueError("cannot generate a reassurance response without any configured entries")
        first = approved_responses[0]
        text = first.get("approved_response")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("configured objection_responses entry has no approved_response text")
        return CustomerResponse(
            message_text=text.strip(),
            channel=channel,
            reason="objection_reassurance",
            related_case_id=case_id,
        )


class UniversalReassuranceResponseGenerator(Protocol):
    def generate(
        self,
        objection_phrase: str,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        service_id: str | None = None,
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse: ...


class DeterministicUniversalReassuranceResponseGenerator:
    """Test/local fallback for the zero-config reassurance path -- used
    whenever the business hasn't authored any objection_responses AND the
    AI-backed universal generator (src.ai.adapters.
    AIUniversalReassuranceResponseGenerator) is unavailable or produced
    invalid output. No AI call, no per-business configuration required,
    never raises. Acknowledgment wording is picked deterministically (a
    stable hash of the objection phrase, not Python's randomized built-in
    hash()) from a small rotating set so a real conversation doesn't see the
    exact same line every time it objects -- and any added factual detail
    comes only from structurally-true facts already in Business DNA
    (fulfillment_type, booking_allowed), never a price or an invented
    promise. customer_tone is accepted for protocol compatibility with
    AIUniversalReassuranceResponseGenerator but intentionally unused here --
    no AI call, so no tone-adaptive rewording to produce."""

    _ACKNOWLEDGMENTS = (
        "That's a completely fair thing to want to be sure about.",
        "Good question to raise now rather than later.",
        "Makes sense that you'd want to think that through.",
        "I hear you -- that's worth addressing before we go further.",
    )

    def generate(
        self,
        objection_phrase: str,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        service_id: str | None = None,
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse:
        digest = sha256(objection_phrase.strip().casefold().encode("utf-8")).digest()
        acknowledgment = self._ACKNOWLEDGMENTS[digest[0] % len(self._ACKNOWLEDGMENTS)]
        fact = self._structural_fact(business_dna, service_id)
        message_text = f"{acknowledgment} {fact}" if fact else acknowledgment
        return CustomerResponse(
            message_text=message_text,
            channel=channel,
            reason="objection_reassurance",
            related_case_id=case_id,
        )

    @staticmethod
    def _structural_fact(business_dna: Mapping[str, object], service_id: str | None) -> str | None:
        if not service_id:
            return None
        services = business_dna.get("services", [])
        if not isinstance(services, list):
            return None
        for service in services:
            if not isinstance(service, Mapping) or service.get("id") != service_id:
                continue
            fulfillment_type = service.get("fulfillment_type")
            if fulfillment_type == "quote_required":
                return "There's no cost or obligation just to get a quote -- we can go over the details first."
            if fulfillment_type == "bookable" and service.get("booking_allowed"):
                return "There's no obligation -- booking a time is just to get things on the calendar."
            if fulfillment_type == "human_review":
                return "A real person will review your specific situation before anything moves forward."
            return None
        return None
