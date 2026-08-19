"""Objection-reassurance wording boundary.

Kept as its own generator (mirroring QuestionGenerator / CustomerResponseGenerator)
rather than folded into either: it answers a different question ("does the customer's
doubt map to something the owner already approved wording for?") than either of those
do, and the AI-backed implementation's job is narrowly to *select and rephrase* one
owner-approved entry, never to draft new reassurance content of its own -- the same
never-invents guarantee the rest of the engine already relies on.
"""

from typing import Mapping, Protocol, Sequence

from src.domain.qualification import CustomerResponse


class ReassuranceResponseGenerator(Protocol):
    def generate(
        self,
        objection_phrase: str,
        approved_responses: Sequence[Mapping[str, object]],
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
    ) -> CustomerResponse: ...


class DeterministicReassuranceResponseGenerator:
    """Test/local fallback: no semantic matching, just the first configured
    entry's approved wording verbatim. The real product path is the
    AI-backed generator (src/ai/adapters.py), which actually selects the
    relevant entry and adapts its tone."""

    def generate(
        self,
        objection_phrase: str,
        approved_responses: Sequence[Mapping[str, object]],
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
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
