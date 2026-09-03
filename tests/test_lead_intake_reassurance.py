"""Objection/reassurance behavior of LeadIntakeService._with_reassurance.

Regression context (live finding, 2026-08-19): the reassurance feature used
to require the business owner to have manually configured at least one
qualification.objection_responses entry -- nothing in onboarding prompts an
owner to do that, so in practice it silently did nothing for every business
(confirmed live: test-law-firm had zero entries configured). This file
covers the fix: a zero-config "universal" reassurance path that grounds its
response in the business's own already-collected Business DNA facts instead
of requiring manual setup, while the owner-authored path (when entries do
exist) keeps working exactly as before. See
claude/universal-sales-cycle-model.md sections 6-7 for the model this
implements.
"""

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.ai.errors import AIInvalidOutputError
from src.domain.qualification import CustomerResponse, IntentResult, IncomingMessage, Urgency
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.engine.lead_intake import LeadIntakeService
from src.engine.question_generator import DeterministicQuestionGenerator


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def business_dna() -> dict:
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        return json.load(file)


def message(external_message_id: str, *, case_id: str | None = None) -> IncomingMessage:
    return IncomingMessage(
        business_id="acme-home-services",
        channel="sms",
        external_message_id=external_message_id,
        customer_name="Ada",
        phone=None,  # left missing so QUALIFYING always generates a question to attach reassurance to
        email=None,
        raw_text="hi",
        timestamp=NOW,
        case_id=case_id,
    )


def objection_intent(objection_phrase: str, **changes: object) -> IntentResult:
    values = {
        "service_requested": "diagnostic-visit",
        "urgency": Urgency.NORMAL,
        "customer_location": "60601",
        "confidence": 0.95,
        "objection_phrase": objection_phrase,
    }
    values.update(changes)
    return IntentResult(**values)  # type: ignore[arg-type]


class _RaisingGenerator:
    """Test double standing in for either reassurance generator protocol --
    both call signatures accept **kwargs-compatible positional args, so one
    stub covers both fallback paths exercised below."""

    def generate(self, *args: object, **kwargs: object) -> CustomerResponse:
        raise AIInvalidOutputError("stub failure")


def test_objection_gets_reassurance_with_no_objection_responses_configured() -> None:
    """The core regression: example Business DNA has no objection_responses
    configured at all (confirmed by the assert below), yet an objection
    still produces a grounded reassurance -- this used to silently no-op."""
    dna = business_dna()
    assert "objection_responses" not in dna["qualification"]

    intake = LeadIntakeService(
        dna,
        DeterministicIntentExtractor({"m1": objection_intent("that's too expensive for me")}),
        DeterministicQuestionGenerator(),
    )
    result = intake.receive(message("m1"))

    assert result.response is not None
    assert result.response.reason == "objection_reassurance_and_missing_information"
    # Grounded in the actually-configured service fact (diagnostic-visit is
    # bookable), not a generic platitude and never a price/discount.
    assert "booking a time" in result.response.message_text
    assert "What is the best phone number to reach you?" in result.response.message_text


def test_owner_configured_objection_responses_still_take_priority() -> None:
    """Regression guard: when the owner HAS configured entries, behavior is
    unchanged -- the owner-authored path is used, not the universal one."""
    dna = deepcopy(business_dna())
    dna["qualification"]["objection_responses"] = [
        {
            "trigger_description": "price pushback",
            "approved_response": "Our diagnostic visit is priced fairly for the work involved.",
        }
    ]
    intake = LeadIntakeService(
        dna,
        DeterministicIntentExtractor({"m1": objection_intent("too expensive")}),
        DeterministicQuestionGenerator(),
    )
    result = intake.receive(message("m1"))

    assert result.response is not None
    assert "priced fairly for the work involved" in result.response.message_text


def test_reassurance_is_capped_per_case() -> None:
    """After MAX_REASSURANCE_ATTEMPTS reassurance turns, the case stops
    getting reassurance text (but the ordinary question flow continues
    unaffected) -- see universal-sales-cycle-model.md section 6."""
    dna = business_dna()
    message_ids = [f"m{i}" for i in range(1, LeadIntakeService.MAX_REASSURANCE_ATTEMPTS + 2)]
    results = {
        message_id: objection_intent(f"objection number {index}")
        for index, message_id in enumerate(message_ids)
    }
    intake = LeadIntakeService(
        dna, DeterministicIntentExtractor(results), DeterministicQuestionGenerator()
    )

    case_id = None
    for index, message_id in enumerate(message_ids, start=1):
        result = intake.receive(message(message_id, case_id=case_id))
        case_id = result.case_id
        assert result.response is not None
        attempts = intake.get_case(case_id).metadata.get("reassurance_attempts", 0)
        if index <= LeadIntakeService.MAX_REASSURANCE_ATTEMPTS:
            assert attempts == index
            assert "\n\n" in result.response.message_text  # reassurance + question
        else:
            assert attempts == LeadIntakeService.MAX_REASSURANCE_ATTEMPTS
            assert "What is the best phone number to reach you?" in result.response.message_text
            assert result.response.sales_technique == "trial_close"


def test_universal_generator_falls_back_to_deterministic_on_invalid_ai_output() -> None:
    """Same resilience pattern as the question generator's own fallback in
    _create_response: an AI-backed generator failing validation must not
    turn into a raw 500 for the customer."""
    dna = business_dna()
    intake = LeadIntakeService(
        dna,
        DeterministicIntentExtractor({"m1": objection_intent("too expensive")}),
        DeterministicQuestionGenerator(),
        universal_reassurance_response_generator=_RaisingGenerator(),
    )
    result = intake.receive(message("m1"))

    assert result.response is not None
    assert "What is the best phone number to reach you?" in result.response.message_text


def test_owner_configured_generator_falls_back_to_deterministic_on_invalid_ai_output() -> None:
    dna = deepcopy(business_dna())
    dna["qualification"]["objection_responses"] = [
        {"trigger_description": "price pushback", "approved_response": "It is worth it."}
    ]
    intake = LeadIntakeService(
        dna,
        DeterministicIntentExtractor({"m1": objection_intent("too expensive")}),
        DeterministicQuestionGenerator(),
        reassurance_response_generator=_RaisingGenerator(),
    )
    result = intake.receive(message("m1"))

    assert result.response is not None
    assert "It is worth it." in result.response.message_text


def test_no_objection_leaves_question_response_untouched() -> None:
    dna = business_dna()
    plain_intent = IntentResult(
        service_requested="diagnostic-visit",
        urgency=Urgency.NORMAL,
        customer_location="60601",
        confidence=0.95,
    )
    intake = LeadIntakeService(
        dna,
        DeterministicIntentExtractor({"m1": plain_intent}),
        DeterministicQuestionGenerator(),
    )
    result = intake.receive(message("m1"))

    assert result.response is not None
    assert result.response.reason == "missing_information"
    assert result.response.message_text == "What is the best phone number to reach you?"
