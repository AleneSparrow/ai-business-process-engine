"""Deterministic sales-technique layer -- selection, objection classification,
and the zero-config wording wrap.

The engine chooses the move; wording generators only apply it. These tests
lock that split: a technique never changes qualification state, never
invents a price/discount, and still works with no per-business playbook.
"""

import json
from pathlib import Path

from src.domain.qualification import IntentResult, IncomingMessage, Urgency
from src.domain.states import ProcessState
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.engine.lead_intake import LeadIntakeService
from src.engine.question_generator import DeterministicQuestionGenerator
from src.engine.sales_technique import (
    ConversationKind,
    ObjectionCategory,
    SalesTechnique,
    classify_objection_category,
    frame_with_technique,
    quote_accept_prompt,
    select_sales_technique,
    slot_lead_in,
)
from src.engine.follow_up import DeterministicFollowUpMessageGenerator
from src.domain.qualification import MissingInformationResult
from datetime import datetime, timezone


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc)


def business_dna() -> dict:
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        return json.load(file)


def test_classifier_maps_common_objections() -> None:
    assert classify_objection_category("that's too expensive for me") is ObjectionCategory.PRICE
    assert classify_objection_category("let me think about it") is ObjectionCategory.TIMING
    assert classify_objection_category("how do I know this is legit") is ObjectionCategory.TRUST
    assert classify_objection_category("I'm shopping around other companies") is ObjectionCategory.COMPARISON
    assert classify_objection_category("not sure this is for me") is ObjectionCategory.FIT
    assert classify_objection_category("I need to ask my husband first") is ObjectionCategory.CONSULT_SOMEONE_ELSE
    assert classify_objection_category("hmm, I don't know") is ObjectionCategory.OTHER
    assert classify_objection_category(None) is ObjectionCategory.NONE
    assert classify_objection_category("   ") is ObjectionCategory.NONE


def test_selector_discovery_on_first_qualifying_turn_even_with_one_field() -> None:
    technique = select_sales_technique(
        kind=ConversationKind.QUALIFYING_QUESTION,
        missing_item_count=1,
        already_qualifying=False,
    )
    assert technique is SalesTechnique.DISCOVERY


def test_selector_trial_close_on_later_turn_with_one_remaining_item() -> None:
    technique = select_sales_technique(
        kind=ConversationKind.QUALIFYING_QUESTION,
        missing_item_count=1,
        already_qualifying=True,
    )
    assert technique is SalesTechnique.TRIAL_CLOSE


def test_selector_discovery_when_several_items_remain() -> None:
    technique = select_sales_technique(
        kind=ConversationKind.QUALIFYING_QUESTION,
        missing_item_count=3,
        already_qualifying=True,
    )
    assert technique is SalesTechnique.DISCOVERY


def test_selector_maps_objection_category_to_technique() -> None:
    assert select_sales_technique(
        kind=ConversationKind.OBJECTION, objection_phrase="that's expensive"
    ) is SalesTechnique.VALUE_REFRAME
    assert select_sales_technique(
        kind=ConversationKind.OBJECTION, objection_phrase="let me think about it"
    ) is SalesTechnique.SOFT_PAUSE
    assert select_sales_technique(
        kind=ConversationKind.OBJECTION, objection_phrase="I need to ask my wife"
    ) is SalesTechnique.CHAMPION


def test_selector_follow_up_breakup_is_the_last_attempt() -> None:
    assert select_sales_technique(
        kind=ConversationKind.FOLLOW_UP,
        follow_up_attempt=2,
        follow_up_maximum_attempts=3,
    ) is SalesTechnique.NURTURE
    assert select_sales_technique(
        kind=ConversationKind.FOLLOW_UP,
        follow_up_attempt=3,
        follow_up_maximum_attempts=3,
    ) is SalesTechnique.BREAKUP


def test_selector_commercial_alternative_vs_commitment() -> None:
    assert select_sales_technique(
        kind=ConversationKind.COMMERCIAL_OFFER,
        slot_count=3,
        commercial_mode="awaiting_slot",
    ) is SalesTechnique.ALTERNATIVE_CLOSE
    assert select_sales_technique(
        kind=ConversationKind.COMMERCIAL_OFFER,
        slot_count=1,
        commercial_mode="awaiting_slot",
    ) is SalesTechnique.SUMMARY_NEXT_STEP
    assert select_sales_technique(
        kind=ConversationKind.COMMERCIAL_OFFER,
        commercial_mode="quote_presented",
    ) is SalesTechnique.COMMITMENT_CLOSE


def test_discovery_framing_is_identity() -> None:
    question = "What is the best phone number to reach you?"
    assert frame_with_technique(SalesTechnique.DISCOVERY, question) == question


def test_trial_close_frames_without_inventing_a_price() -> None:
    framed = frame_with_technique(
        SalesTechnique.TRIAL_CLOSE, "What is the best phone number to reach you?"
    )
    assert framed.startswith("One last detail and we can move forward.")
    assert "phone number" in framed
    assert "$" not in framed
    assert "%" not in framed
    assert "discount" not in framed.casefold()


def test_value_reframe_uses_only_supplied_structural_fact() -> None:
    framed = frame_with_technique(
        SalesTechnique.VALUE_REFRAME,
        "",
        fact="There's no obligation -- booking a time is just to get things on the calendar.",
    )
    assert "Cost is a fair thing" in framed
    assert "booking a time" in framed
    assert "$" not in framed


def test_slot_lead_in_is_an_alternative_close() -> None:
    assert slot_lead_in(reschedule=False, slot_count=3) == (
        "Which of these times works better for you:"
    )
    assert slot_lead_in(reschedule=True, slot_count=2).startswith("Which of these new times")
    assert slot_lead_in(reschedule=False, slot_count=1) == "Here's a time that works:"


def test_quote_accept_prompt_asks_for_yes_or_no_without_sweetening() -> None:
    prompt = quote_accept_prompt()
    assert "accept" in prompt
    assert "decline" in prompt
    assert "discount" not in prompt.casefold()
    assert "free" not in prompt.casefold()


def _intake_with(intent: IntentResult) -> LeadIntakeService:
    return LeadIntakeService(
        business_dna(),
        DeterministicIntentExtractor({"m1": intent}),
        DeterministicQuestionGenerator(),
    )


def _message(**changes: object) -> IncomingMessage:
    values = {
        "business_id": "acme-home-services",
        "channel": "sms",
        "external_message_id": "m1",
        "customer_name": "Ada",
        "phone": None,
        "email": None,
        "raw_text": "hi",
        "timestamp": NOW,
    }
    values.update(changes)
    return IncomingMessage(**values)  # type: ignore[arg-type]


def test_price_objection_uses_value_reframe_and_stays_qualifying() -> None:
    intake = _intake_with(IntentResult(
        service_requested="diagnostic-visit",
        urgency=Urgency.NORMAL,
        customer_location="60601",
        confidence=0.95,
        objection_phrase="that's too expensive for me",
    ))
    result = intake.receive(_message())
    assert result.current_state is ProcessState.QUALIFYING
    assert result.qualification.qualified is False
    assert result.response is not None
    assert result.response.sales_technique == SalesTechnique.VALUE_REFRAME.value
    assert "Cost is a fair thing" in result.response.message_text
    assert "booking a time" in result.response.message_text
    assert "What is the best phone number to reach you?" in result.response.message_text
    assert "$" not in result.response.message_text
    assert "free" not in result.response.message_text.casefold()


def test_plain_first_question_stays_discovery_and_keeps_configured_wording() -> None:
    intake = _intake_with(IntentResult(
        service_requested="diagnostic-visit",
        urgency=Urgency.NORMAL,
        customer_location="60601",
        confidence=0.95,
    ))
    result = intake.receive(_message())
    assert result.response is not None
    assert result.response.sales_technique == SalesTechnique.DISCOVERY.value
    assert result.response.message_text == "What is the best phone number to reach you?"


def test_later_single_field_uses_trial_close() -> None:
    intake = LeadIntakeService(
        business_dna(),
        DeterministicIntentExtractor({
            "m1": IntentResult(
                service_requested="diagnostic-visit",
                urgency=Urgency.NORMAL,
                customer_location="60601",
                confidence=0.95,
            ),
            "m2": IntentResult(confidence=0.95),
        }),
        DeterministicQuestionGenerator(),
    )
    first = intake.receive(_message(external_message_id="m1"))
    second = intake.receive(_message(external_message_id="m2", case_id=first.case_id))
    assert second.current_state is ProcessState.QUALIFYING
    assert second.response is not None
    assert second.response.sales_technique == SalesTechnique.TRIAL_CLOSE.value
    assert second.response.message_text.startswith("One last detail")
    assert "phone number" in second.response.message_text
    assert first.qualification.missing_fields == second.qualification.missing_fields


def test_consult_objection_uses_champion_technique() -> None:
    intake = _intake_with(IntentResult(
        service_requested="diagnostic-visit",
        urgency=Urgency.NORMAL,
        customer_location="60601",
        confidence=0.95,
        objection_phrase="I need to ask my husband first",
    ))
    result = intake.receive(_message(raw_text="I need to ask my husband first"))
    assert result.response is not None
    assert result.response.sales_technique == SalesTechnique.CHAMPION.value
    assert "someone else" in result.response.message_text


def test_last_follow_up_uses_breakup_without_a_new_offer() -> None:
    generator = DeterministicFollowUpMessageGenerator()
    missing = MissingInformationResult(("phone",), ())
    dna = {
        "business": {"name": "Acme Home Services"},
        "customer_information": {
            "field_questions": {"phone": "What is the best number to reach you?"},
        },
    }
    response = generator.generate(
        missing, dna, "sms", "case-1", attempt_number=3, maximum_attempts=3
    )
    assert response.sales_technique == SalesTechnique.BREAKUP.value
    assert "close this out" in response.message_text
    assert "best number to reach you" in response.message_text
    assert "discount" not in response.message_text.casefold()
    assert "urgent" not in response.message_text.casefold()
