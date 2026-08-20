"""Emotion/style adaptation layer (universal-sales-cycle-model.md section 7).

Covers the "живая адаптация к клиенту" work: a deterministic customer_tone
classification (mirroring how objection_phrase already works) threaded from
intent extraction through to every response-generation call, used only to
adapt HOW a response is worded -- never WHAT is said. This file checks the
threading and the AI-adapter wiring; it does not (and cannot, without a real
model) check actual generated wording quality -- that was verified live
against production (see claude/universal-sales-cycle-model.md section 10).
"""

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import pytest

from src.ai.adapters import AIIntentExtractor, AIQuestionGenerator
from src.ai.fake_provider import FakeAIProvider
from src.domain.qualification import (
    CustomerResponse,
    CustomerTone,
    IncomingMessage,
    IntentResult,
    MissingInformationResult,
    Urgency,
)
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.engine.lead_intake import LeadIntakeService
from src.engine.question_generator import DeterministicQuestionGenerator


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)


def business_dna() -> dict:
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        return json.load(file)


def message(external_message_id: str, *, raw_text: str = "hi", case_id: str | None = None) -> IncomingMessage:
    return IncomingMessage(
        business_id="acme-home-services",
        channel="sms",
        external_message_id=external_message_id,
        customer_name="Ada",
        phone=None,  # missing so QUALIFYING always generates a question to inspect
        email=None,
        raw_text=raw_text,
        timestamp=NOW,
        case_id=case_id,
    )


def intent_output(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "service_id": "diagnostic-visit",
        "unsupported_service": False,
        "unsupported_service_name": None,
        "urgency": "normal",
        "customer_location": "60601",
        "preferred_time": None,
        "notes": None,
        "customer_name": None,
        "phone": None,
        "email": None,
        "confidence": 0.95,
        "requires_human": False,
        "qualification_answers": [],
        "objection_phrase": None,
        "customer_tone": "neutral",
    }
    value.update(changes)
    return value


class _RecordingQuestionGenerator:
    """Spy standing in for QuestionGenerator -- records exactly what
    customer_message/customer_tone LeadIntakeService threads through, then
    delegates to the real deterministic renderer so the response is still
    valid."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._real = DeterministicQuestionGenerator()

    def generate(
        self,
        missing: MissingInformationResult,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        customer_message: str = "",
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse:
        self.calls.append({"customer_message": customer_message, "customer_tone": customer_tone})
        return self._real.generate(missing, business_dna, channel, case_id, customer_message, customer_tone)


class _RecordingUniversalReassuranceGenerator:
    """Same spy pattern for the reassurance path."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        objection_phrase: str,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        service_id: str | None = None,
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse:
        self.calls.append({"customer_tone": customer_tone})
        return CustomerResponse(
            message_text="Fair point.",
            channel=channel,
            reason="objection_reassurance",
            related_case_id=case_id,
        )


def objection_intent(customer_tone: CustomerTone, **changes: object) -> IntentResult:
    values: dict[str, object] = {
        "service_requested": "diagnostic-visit",
        "urgency": Urgency.NORMAL,
        "customer_location": "60601",
        "confidence": 0.95,
        "objection_phrase": "that's too expensive",
        "customer_tone": customer_tone,
    }
    values.update(changes)
    return IntentResult(**values)  # type: ignore[arg-type]


def test_intent_result_defaults_customer_tone_to_neutral() -> None:
    """DeterministicIntentExtractor never classifies tone -- IntentResult's
    own default (NEUTRAL) is what carries the field, not a crash or None."""
    dna = business_dna()
    extractor = DeterministicIntentExtractor()
    result = extractor.extract(message("m1", raw_text="I need help with a diagnostic visit"), dna)
    assert result.customer_tone is CustomerTone.NEUTRAL


def test_ai_intent_extractor_returns_classified_customer_tone() -> None:
    # customer_location is dropped to None here: AIIntentExtractor._evidenced
    # requires every non-null field to literally appear in the customer's
    # raw text (anti-hallucination guarantee), and intent_output()'s default
    # "60601" has nothing to do with what this test is checking -- leaving
    # it in would raise AIInvalidOutputError for an unrelated reason and
    # collapse the whole result (confidence=0.0, customer_tone reset to
    # NEUTRAL), making this test fail for the wrong reason.
    provider = FakeAIProvider([intent_output(customer_tone="anxious", customer_location=None)])
    extractor = AIIntentExtractor(provider)
    # Message must actually contain evidence for the scripted service_id
    # ("diagnostic-visit") -- AIIntentExtractor._resolve_service rejects an
    # unevidenced service and the whole result collapses to a fallback
    # (confidence=0.0, customer_tone reset to NEUTRAL), which would make
    # this test pass for the wrong reason if the message didn't mention it.
    result = extractor.extract(
        message("m1", raw_text="I'm really worried, is a diagnostic visit going to be ok?"), business_dna()
    )
    assert result.customer_tone is CustomerTone.ANXIOUS


def test_ai_question_generator_forwards_real_customer_message_and_tone() -> None:
    """Regression guard for the found bug: AIQuestionGenerator used to call
    clarification_prompt with a hardcoded empty customer_message, so there
    was nothing for tone adaptation to mirror even once wired up."""
    provider = FakeAIProvider([{"addressed_items": ["field:phone"], "message_text": "What's the best number to reach you?"}])
    generator = AIQuestionGenerator(provider)
    missing = MissingInformationResult(("phone",), ())
    generator.generate(
        missing,
        business_dna(),
        "sms",
        "case-1",
        customer_message="ugh fine, whatever, here",
        customer_tone=CustomerTone.IRRITATED,
    )
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert "ugh fine, whatever, here" in request.user_prompt
    assert '"customer_tone":"irritated"' in request.user_prompt


def test_lead_intake_threads_customer_message_and_tone_to_question_generator() -> None:
    dna = business_dna()
    spy = _RecordingQuestionGenerator()
    extracted = IntentResult(
        service_requested="diagnostic-visit",
        urgency=Urgency.NORMAL,
        customer_location="60601",
        confidence=0.95,
        customer_tone=CustomerTone.URGENT,
    )
    intake = LeadIntakeService(
        dna,
        DeterministicIntentExtractor({"m1": extracted}),
        spy,
    )
    result = intake.receive(message("m1", raw_text="need this ASAP please"))

    assert result.response is not None
    assert len(spy.calls) == 1
    assert spy.calls[0]["customer_message"] == "need this ASAP please"
    assert spy.calls[0]["customer_tone"] is CustomerTone.URGENT


def test_merge_intent_preserves_customer_tone_across_turns() -> None:
    """Regression guard: the merged IntentResult used to omit customer_tone
    entirely, which would silently reset every merged turn back to NEUTRAL
    regardless of what AIIntentExtractor actually classified."""
    dna = business_dna()
    spy = _RecordingQuestionGenerator()
    intake = LeadIntakeService(
        dna,
        DeterministicIntentExtractor({
            "m1": IntentResult(
                service_requested="diagnostic-visit",
                urgency=Urgency.NORMAL,
                confidence=0.95,
                customer_tone=CustomerTone.PLAYFUL,
            ),
        }),
        spy,
    )
    intake.receive(message("m1", raw_text="lol sure why not, sign me up :)"))

    assert spy.calls[-1]["customer_tone"] is CustomerTone.PLAYFUL


def test_reassurance_generator_receives_customer_tone() -> None:
    dna = business_dna()
    universal_spy = _RecordingUniversalReassuranceGenerator()
    intake = LeadIntakeService(
        dna,
        DeterministicIntentExtractor({"m1": objection_intent(CustomerTone.ANXIOUS)}),
        DeterministicQuestionGenerator(),
        universal_reassurance_response_generator=universal_spy,
    )
    result = intake.receive(message("m1", raw_text="I'm nervous this is going to cost a lot"))

    assert result.response is not None
    assert len(universal_spy.calls) == 1
    assert universal_spy.calls[0]["customer_tone"] is CustomerTone.ANXIOUS


def test_deterministic_generators_ignore_tone_without_erroring() -> None:
    """Every deterministic (non-AI) generator must accept customer_tone for
    protocol compatibility and simply ignore it -- no AI call, nothing to
    adapt. This is the offline/fallback path, so it must never raise on the
    new parameter."""
    dna = business_dna()
    intake = LeadIntakeService(
        dna,
        DeterministicIntentExtractor({
            "m1": IntentResult(
                service_requested="diagnostic-visit",
                urgency=Urgency.NORMAL,
                customer_location="60601",
                confidence=0.95,
                customer_tone=CustomerTone.IRRITATED,
            ),
        }),
        DeterministicQuestionGenerator(),
    )
    result = intake.receive(message("m1"))
    assert result.response is not None
    assert result.response.message_text  # rendered fine, tone silently ignored
