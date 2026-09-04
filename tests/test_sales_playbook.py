"""Closed-cycle sales: the engine replaces the person processing leads."""

from dataclasses import replace

from src.domain.business_dna_builder import OnboardingInput, OnboardingService, build_business_dna
from src.domain.qualification import CustomerTone
from src.domain.states import ProcessState
from src.engine.commercial import CommercialPathSelector
from src.engine.sales_playbook import (
    DialogueSnapshot,
    ObjectionKind,
    SalesMove,
    append_close_ask,
    classify_objection,
    close_ask_for_fulfillment,
    close_ask_for_objection,
    next_move,
    nurture_copy,
)


def test_close_ask_never_invents_a_price() -> None:
    assert "$" not in close_ask_for_fulfillment("bookable")
    assert "$" not in close_ask_for_fulfillment("quote_required")
    assert "accept" in close_ask_for_fulfillment("quote_required")


def test_nurture_copy_reasks_for_the_commitment_already_on_the_table() -> None:
    assert "accept" in nurture_copy(ProcessState.QUOTED, missing_complete=True)
    assert "1, 2, or 3" in nurture_copy(ProcessState.QUALIFIED, missing_complete=True)
    assert "still interested" not in nurture_copy(
        ProcessState.QUALIFYING, missing_complete=True
    ).casefold()


def test_objection_classifier_uses_the_customers_words() -> None:
    assert classify_objection("that's too expensive for me") is ObjectionKind.PRICE
    assert classify_objection("I need to think about it") is ObjectionKind.TIMING
    assert classify_objection("I should ask my partner first") is ObjectionKind.CONSULT_SOMEONE_ELSE
    assert classify_objection("") is ObjectionKind.OTHER


def test_timing_objection_holds_a_slot_instead_of_ending_the_turn() -> None:
    ask = close_ask_for_objection(ObjectionKind.TIMING, "bookable")
    assert "hold a time" in ask
    assert "still interested" not in ask


def test_tone_does_not_change_the_sales_move() -> None:
    base = DialogueSnapshot(
        state=ProcessState.QUALIFIED,
        missing_complete=True,
        has_objection=False,
        commercial_mode=None,
        requires_human=False,
        customer_tone=CustomerTone.NEUTRAL,
        inbound_turns=3,
    )
    irritated = replace(base, customer_tone=CustomerTone.IRRITATED)
    assert next_move(base) is SalesMove.OFFER_COMMITMENT
    assert next_move(irritated) is SalesMove.OFFER_COMMITMENT


def test_append_close_ask_never_invents_a_price_and_does_not_duplicate() -> None:
    ack = "That's a fair thing to want to be sure about."
    closed = append_close_ask(ack, "that's too expensive", "bookable")
    assert closed.startswith(ack)
    assert "hold a time" in closed
    assert "$" not in closed
    assert append_close_ask(closed, "that's too expensive", "bookable") == closed


def test_emergency_is_the_only_default_handoff() -> None:
    snapshot = DialogueSnapshot(
        state=ProcessState.QUALIFYING,
        missing_complete=True,
        has_objection=False,
        commercial_mode=None,
        requires_human=True,
        inbound_turns=1,
    )
    assert next_move(snapshot) is SalesMove.ESCALATE_SAFETY


def test_qualified_without_a_slot_picks_offer_not_crm_file() -> None:
    snapshot = DialogueSnapshot(
        state=ProcessState.QUALIFIED,
        missing_complete=True,
        has_objection=False,
        commercial_mode=None,
        requires_human=False,
        inbound_turns=4,
    )
    assert next_move(snapshot) is SalesMove.OFFER_COMMITMENT


def test_open_quote_is_a_trial_close() -> None:
    snapshot = DialogueSnapshot(
        state=ProcessState.QUOTED,
        missing_complete=True,
        has_objection=False,
        commercial_mode="quote",
        requires_human=False,
        inbound_turns=5,
    )
    assert next_move(snapshot) is SalesMove.TRIAL_CLOSE


def test_zero_config_onboarding_selects_booking_not_human_review() -> None:
    dna = build_business_dna(OnboardingInput(
        business_id="zero-config-close",
        business_name="Northstar Home Services",
        industry="Home services",
        tone="Friendly & direct",
        services=(OnboardingService("Heating repair", ("Is the system running?",)),),
        service_zip_codes=("10001",),
    ))
    service_id = dna["services"][0]["id"]
    assert dna["booking"]["enabled"] is True
    assert dna["services"][0]["fulfillment_type"] == "bookable"
    assert CommercialPathSelector().select(dna, service_id).value == "booking"


def test_flywheel_sells_itself_on_the_same_zero_config_path() -> None:
    dna = build_business_dna(OnboardingInput(
        business_id="flywheel",
        business_name="Flywheel",
        industry="SaaS / Software",
        description="Takes an inbound inquiry to a booked or quoted deal without a person processing each lead",
        tone="Friendly & direct",
        services=(
            OnboardingService(
                "Product demo",
                ("How many inbound leads do you handle in a typical week?",),
                "Watch the engine take a real inbound lead from first message to a booked time",
            ),
        ),
        service_zip_codes=(),
        enforce_service_area=False,
    ))
    service_id = dna["services"][0]["id"]
    assert CommercialPathSelector().select(dna, service_id).value == "booking"
    assert "team will follow up" not in dna["chat_widget"]["qualified_message"].casefold()


def test_ai_universal_reassurance_appends_the_engine_close() -> None:
    """The model acknowledges; the playbook still asks for the next step."""
    from src.ai.adapters import AIUniversalReassuranceResponseGenerator
    from src.ai.fake_provider import FakeAIProvider
    from src.ai.models import UniversalReassuranceOutput

    dna = build_business_dna(OnboardingInput(
        business_id="zero-config-close",
        business_name="Northstar Home Services",
        industry="Home services",
        tone="Friendly & direct",
        services=(OnboardingService("Heating repair", ("Is the system running?",)),),
        service_zip_codes=("10001",),
    ))
    provider = FakeAIProvider(
        [
            UniversalReassuranceOutput(
                objection_category="timing",
                message_text="It makes sense to pause and think it through.",
            )
        ]
    )
    response = AIUniversalReassuranceResponseGenerator(provider).generate(
        "I need to think about it",
        dna,
        "webchat",
        "case-1",
        service_id=dna["services"][0]["id"],
    )
    assert "think it through" in response.message_text
    assert "hold a time" in response.message_text
    assert "$" not in response.message_text

