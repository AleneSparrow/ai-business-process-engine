import copy
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from src.domain.commercial import (
    Booking,
    BookingRequest,
    BookingStatus,
    PaymentRequest,
    PaymentStatus,
    PaymentType,
    QuoteStatus,
)
from src.domain.models import Lead, ProcessCase
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.engine.commercial import (
    CommercialPathSelector,
    DeterministicAvailabilityEngine,
    DeterministicPostSaleReplyInterpreter,
    DeterministicPricingEngine,
    DeterministicQuoteReplyInterpreter,
    DeterministicSlotPreferenceInterpreter,
    payment_amount,
)
from src.persistence.commercial_service import CommercialWorkflowService
from src.persistence.sqlalchemy_models import Base, BookingRow, PaymentRequestRow, QuoteRow
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


ROOT = Path(__file__).parents[1]
UTC = timezone.utc
NOW = datetime(2026, 8, 11, 14, 0, tzinfo=UTC)


def load_dna() -> dict:
    return json.loads((ROOT / "config" / "business_dna.example.json").read_text())


def make_factory(tmp_path, service_id: str):
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / (service_id + '.db')}")
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    dna = load_dna()
    lead = Lead(
        f"lead-{service_id}",
        "Ada",
        None,
        "+13125550100",
        {
            "service_requested": service_id,
            "customer_location": "60601",
        },
    )
    case = ProcessCase(
        f"case-{service_id}",
        dna["business"]["id"],
        lead,
        ProcessState.QUALIFIED,
        NOW,
        NOW,
    )
    with factory() as uow:
        uow.businesses.add(Business(dna["business"]["id"], "Acme", NOW, NOW))
        uow.business_dna.add_version(dna["business"]["id"], dna)
        uow.leads.add(dna["business"]["id"], lead, NOW)
        uow.cases.add(case)
        uow.commit()
    return engine, factory, dna, case.case_id


def test_bookable_case_proposes_bounded_real_slots_and_books_second_option(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        response = service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        assert response.reason == "booking_slots_proposed"
        assert response.message_text.count("\n") == 3
        proposed = tuple(metadata["commercial"]["slots"])
        assert len(proposed) == 3
        uow.commit()

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        response = service.handle_message(
            uow, case, dna, metadata, "The second option works", occurred_at=NOW
        )
        uow.commit()
        assert response.reason == "booking_confirmed"
        assert case.current_state is ProcessState.WON

    with factory() as uow:
        booking = uow.bookings.get_for_case(dna["business"]["id"], case_id)
        payment = uow.session.scalar(select(PaymentRequestRow))
        assert booking is not None
        assert booking.start_at.isoformat() == proposed[1]["start_at"]
        assert booking.status is BookingStatus.CONFIRMED
        assert payment is not None
        assert payment.status == PaymentStatus.READY.value
        assert payment.amount == Decimal("25.80")
    engine.dispose()


def test_availability_respects_hours_duration_buffers_capacity_and_dst() -> None:
    dna = load_dna()
    engine = DeterministicAvailabilityEngine()
    request = BookingRequest(
        "acme-home-services",
        "case-a",
        "lead-a",
        "diagnostic-visit",
        NOW,
        NOW + timedelta(days=3),
        3,
    )
    slots = engine.available_slots(request, dna, (), now=NOW)
    assert len(slots) == 3
    assert all(slot.end_at - slot.start_at == timedelta(minutes=60) for slot in slots)
    local_starts = [slot.start_at.astimezone(ZoneInfo("America/Chicago")) for slot in slots]
    assert all(9 <= start.hour < 16 for start in local_starts)

    occupied = Booking(
        "booking-a",
        "acme-home-services",
        "other-case",
        "other-lead",
        "diagnostic-visit",
        slots[0].start_at,
        slots[0].end_at,
        slots[0].timezone,
        BookingStatus.CONFIRMED,
        NOW,
        NOW,
    )
    remaining = engine.available_slots(request, dna, (occupied,), now=NOW)
    assert slots[0].start_at not in {slot.start_at for slot in remaining}

    dst_dna = copy.deepcopy(dna)
    dst_dna["booking"].update({
        "allowed_days": ["sunday"],
        "allowed_times": [{"starts": "01:00", "ends": "04:00"}],
        "slot_interval_minutes": 30,
        "buffer_before_minutes": 0,
        "buffer_after_minutes": 0,
        "minimum_notice_minutes": 0,
    })
    dst_dna["business_hours"]["sunday"] = [{"opens": "01:00", "closes": "04:00"}]
    dst_request = BookingRequest(
        "acme-home-services",
        "dst-case",
        "dst-lead",
        "diagnostic-visit",
        datetime(2026, 3, 8, 6, 0, tzinfo=UTC),
        datetime(2026, 3, 8, 9, 0, tzinfo=UTC),
        10,
    )
    dst_slots = engine.available_slots(
        dst_request, dst_dna, (), now=datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    )
    local_hours = [
        slot.start_at.astimezone(ZoneInfo("America/Chicago")).hour for slot in dst_slots
    ]
    assert 2 not in local_hours
    assert len({slot.start_at for slot in dst_slots}) == len(dst_slots)


def test_slot_interpreter_never_invents_customer_time() -> None:
    dna = load_dna()
    slots = DeterministicAvailabilityEngine().available_slots(
        BookingRequest(
            "acme-home-services",
            "case-a",
            "lead-a",
            "diagnostic-visit",
            NOW,
            NOW + timedelta(days=2),
            3,
        ),
        dna,
        (),
        now=NOW,
    )
    interpreter = DeterministicSlotPreferenceInterpreter()
    assert interpreter.interpret("The second option works", slots, now=NOW).selected == slots[1]
    invented = interpreter.interpret("Sunday at midnight", slots, now=NOW)
    assert invented.selected is None


def test_post_sale_interpreter_reads_payment_done_and_decline() -> None:
    interpreter = DeterministicPostSaleReplyInterpreter()
    assert interpreter.interpret("I paid just now").signal == "payment_received"
    assert interpreter.interpret("The visit went well").signal == "done"
    assert interpreter.interpret("I uploaded the files").signal == "done"
    assert interpreter.interpret("No, I won't do that").signal == "declined"
    assert interpreter.interpret("Where do I upload it?").signal == "question"
    assert interpreter.interpret("I'll pay later").signal == "unclear"


def test_quote_collects_fact_uses_decimal_accepts_and_prepares_payment(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "equipment-replacement")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        response = service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        assert response.reason == "pricing_input_required"
        assert case.current_state is ProcessState.QUALIFIED
        uow.commit()

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        response = service.handle_message(
            uow, case, dna, metadata, "2", occurred_at=NOW
        )
        uow.commit()
        assert response.reason == "quote_presented"
        assert "USD 5500.00" in response.message_text
        assert case.current_state is ProcessState.QUOTED

    with factory() as uow:
        quote = uow.quotes.get_for_case(dna["business"]["id"], case_id)
        assert quote is not None
        assert quote.total == Decimal("5500.00")
        assert quote.status is QuoteStatus.PRESENTED

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        response = service.handle_message(
            uow, case, dna, metadata, "Yes, let's do it", occurred_at=NOW
        )
        uow.commit()
        assert response.reason == "quote_accepted"
        assert case.current_state is ProcessState.WON

    with factory() as uow:
        quote = uow.quotes.get_for_case(dna["business"]["id"], case_id)
        payment = uow.session.scalar(select(PaymentRequestRow))
        assert quote.status is QuoteStatus.ACCEPTED
        assert payment.amount == Decimal("1100.00")
        assert uow.session.scalar(select(func.count()).select_from(QuoteRow)) == 1
    engine.dispose()


def test_validated_numeric_qualification_fact_can_satisfy_pricing_input() -> None:
    lead = Lead(
        "lead-pricing-fact",
        attributes={
            "service_requested": "equipment-replacement",
            "qualification_answers": {
                "equipment_units": "2",
                "residential": True,
            },
        },
    )
    case = ProcessCase(
        "case-pricing-fact",
        "business",
        lead,
        ProcessState.QUALIFIED,
        NOW,
        NOW,
    )
    assert CommercialWorkflowService._pricing_inputs(case) == {
        "equipment_units": Decimal("2")
    }


def test_quote_threshold_requires_human_and_money_rules_use_decimal(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "equipment-replacement")
    dna["services"][1]["quoting"]["human_approval_threshold"] = "1000.00"
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        response = service.handle_message(uow, case, dna, metadata, "2", occurred_at=NOW)
        assert response.requires_human is True
        assert case.current_state is ProcessState.NEEDS_HUMAN
        uow.commit()

    assert payment_amount(Decimal("129.00"), dna["payment"]) == (
        Decimal("25.80"),
        "DEPOSIT",
    )
    assert payment_amount(Decimal("0.00"), dna["payment"]) is None
    invalid_fixed = copy.deepcopy(dna["payment"])
    invalid_fixed["deposit"] = {
        "required": True,
        "type": "fixed",
        "percentage": None,
        "fixed_amount": "0.00",
    }
    with pytest.raises(ValueError, match="greater than zero"):
        payment_amount(Decimal("129.00"), invalid_fixed)
    pricing = DeterministicPricingEngine().calculate(
        load_dna()["services"][1], "USD", {"equipment_units": Decimal("2")}
    )
    assert pricing.total == Decimal("5500.00")
    fixed_service = copy.deepcopy(load_dna()["services"][1])
    fixed_service["quoting"] = {
        "pricing_type": "fixed",
        "automatic_quote_allowed": True,
        "required_pricing_inputs": [],
        "pricing_input_questions": {},
        "fixed_price": "180.00",
        "human_approval_threshold": "500.00",
    }
    fixed = DeterministicPricingEngine().calculate(fixed_service, "USD", {})
    assert fixed.total == Decimal("180.00")
    assert fixed.requires_human is False
    fixed_service["quoting"]["automatic_quote_allowed"] = False
    assert DeterministicPricingEngine().calculate(
        fixed_service, "USD", {}
    ).requires_human is True
    fixed_service["quoting"]["fixed_price"] = "180.001"
    with pytest.raises(ValueError, match="two decimal"):
        DeterministicPricingEngine().calculate(fixed_service, "USD", {})
    engine.dispose()


def test_expired_quote_cannot_be_accepted(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "equipment-replacement")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(uow, case, dna, metadata, "1", occurred_at=NOW)
        uow.commit()
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        response = service.handle_message(
            uow, case, dna, metadata, "I accept", occurred_at=NOW + timedelta(days=15)
        )
        assert response.reason == "quote_expired"
        assert case.current_state is ProcessState.LOST
        uow.commit()
    with factory() as uow:
        quote = uow.quotes.get_for_case(dna["business"]["id"], case_id)
        assert quote.status is QuoteStatus.EXPIRED
    engine.dispose()


def test_quote_rejection_is_persisted_and_moves_case_to_lost(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "equipment-replacement")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(uow, case, dna, metadata, "1", occurred_at=NOW)
        response = service.handle_message(
            uow, case, dna, metadata, "No thanks", occurred_at=NOW
        )
        assert response.reason == "quote_rejected"
        assert case.current_state is ProcessState.LOST
        uow.commit()
    with factory() as uow:
        quote = uow.quotes.get_for_case(dna["business"]["id"], case_id)
        assert quote.status is QuoteStatus.REJECTED
    engine.dispose()


@pytest.mark.parametrize("customer_reply", ["I did it", "I uploaded the documents"])
def test_direct_next_step_customer_confirmation_closes_the_win(tmp_path, customer_reply: str) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service_config = dna["services"][0]
    service_config.update({
        "fulfillment_type": "direct_sale",
        "booking_allowed": False,
        "direct_next_step_message": "Upload documents at https://example.test/upload.",
    })
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        first = service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        assert first.reason == "direct_next_step"
        response = service.handle_message(
            uow, case, dna, metadata, customer_reply, occurred_at=NOW + timedelta(minutes=1)
        )
        assert response.reason == "direct_next_step_confirmed"
        assert case.current_state is ProcessState.WON
        assert response.requires_human is False
        uow.commit()
    engine.dispose()


def test_direct_next_step_question_repeats_the_instruction(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service_config = dna["services"][0]
    service_config.update({
        "fulfillment_type": "direct_sale",
        "booking_allowed": False,
        "direct_next_step_message": "Upload documents at https://example.test/upload.",
    })
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        response = service.handle_message(
            uow, case, dna, metadata, "Where do I upload it?", occurred_at=NOW + timedelta(minutes=1)
        )
        assert response.requires_human is False
        assert case.current_state is ProcessState.QUALIFIED
        assert "https://example.test/upload" in response.message_text
        uow.commit()
    engine.dispose()


def test_direct_next_step_decline_closes_as_lost(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service_config = dna["services"][0]
    service_config.update({
        "fulfillment_type": "direct_sale",
        "booking_allowed": False,
        "direct_next_step_message": "Upload documents at https://example.test/upload.",
    })
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        response = service.handle_message(
            uow, case, dna, metadata, "No, I won't do that", occurred_at=NOW + timedelta(minutes=1)
        )
        assert response.reason == "direct_next_step_declined"
        assert case.current_state is ProcessState.LOST
        uow.commit()
    engine.dispose()


def test_ambiguous_quote_response_is_reasked_then_pauses_for_human(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "equipment-replacement")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(uow, case, dna, metadata, "1", occurred_at=NOW)
        for attempt in range(CommercialWorkflowService.MAX_QUOTE_REPLY_ATTEMPTS):
            response = service.handle_message(
                uow, case, dna, metadata, "Maybe, I am not sure", occurred_at=NOW
            )
            assert response.reason == "quote_reply_unclear"
            assert response.requires_human is False
            assert case.current_state is ProcessState.QUOTED
            assert metadata["commercial"]["quote_reply_attempts"] == attempt + 1

        response = service.handle_message(
            uow, case, dna, metadata, "Maybe, I am not sure", occurred_at=NOW
        )
        assert response.requires_human is True
        assert case.current_state is ProcessState.NEEDS_HUMAN
        assert case.pending_transition is ProcessState.FOLLOW_UP
        uow.commit()
    engine.dispose()


def test_payment_threshold_and_lazy_expiration_are_safe(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    dna["payment"]["human_approval_above"] = "100.00"
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        response = service.handle_message(uow, case, dna, metadata, "1", occurred_at=NOW)
        assert response.requires_human is True
        assert case.current_state is ProcessState.NEEDS_HUMAN
        uow.commit()
    with factory() as uow:
        payment = uow.session.scalar(select(PaymentRequestRow))
        assert payment.status == PaymentStatus.PENDING.value
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.expire_due_items(
            uow, case, occurred_at=NOW + timedelta(hours=73)
        )
        uow.commit()
    with factory() as uow:
        payment = uow.session.scalar(select(PaymentRequestRow))
        assert payment.status == PaymentStatus.EXPIRED.value
    engine.dispose()


def test_required_payment_cannot_be_bypassed_by_missing_deterministic_price(
    tmp_path,
) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    dna["services"][0]["pricing"] = {
        "model": "custom_quote",
        "tax_included": False,
    }
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        response = service.handle_message(uow, case, dna, metadata, "1", occurred_at=NOW)
        assert response.requires_human is True
        assert case.current_state is ProcessState.NEEDS_HUMAN
        assert uow.session.scalar(select(func.count()).select_from(BookingRow)) == 0
        uow.commit()
    engine.dispose()


def test_booking_cancel_and_reschedule_preserve_single_booking(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    dna["booking"]["rescheduling"]["minimum_notice_hours"] = 0
    dna["booking"]["cancellation"]["minimum_notice_hours"] = 0
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(uow, case, dna, metadata, "1", occurred_at=NOW)
        uow.commit()
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.handle_message(uow, case, dna, metadata, "reschedule", occurred_at=NOW)
        response = service.handle_message(uow, case, dna, metadata, "2", occurred_at=NOW)
        assert response.reason == "booking_rescheduled"
        uow.commit()
    with factory() as uow:
        assert uow.session.scalar(select(func.count()).select_from(BookingRow)) == 1
        case = uow.cases.get(dna["business"]["id"], case_id)
        response = service.handle_message(uow, case, dna, metadata, "cancel", occurred_at=NOW)
        assert response.reason == "booking_cancelled"
        assert case.current_state is ProcessState.CANCELLED
        uow.commit()
    engine.dispose()


def test_commercial_path_is_business_dna_authority() -> None:
    dna = load_dna()
    selector = CommercialPathSelector()
    assert selector.select(dna, "diagnostic-visit").value == "booking"
    assert selector.select(dna, "equipment-replacement").value == "quote"
    dna["services"][0]["booking_allowed"] = False
    assert selector.select(dna, "diagnostic-visit").value == "human_review"


def test_commercial_models_reject_unsafe_money_time_and_mutable_defaults() -> None:
    first = Booking(
        "booking-one",
        "business",
        "case-one",
        "lead-one",
        "service",
        NOW,
        NOW + timedelta(hours=1),
        "UTC",
        BookingStatus.CONFIRMED,
        NOW,
        NOW,
    )
    second = Booking(
        "booking-two",
        "business",
        "case-two",
        "lead-two",
        "service",
        NOW,
        NOW + timedelta(hours=1),
        "UTC",
        BookingStatus.CONFIRMED,
        NOW,
        NOW,
    )
    first.metadata["changed"] = True
    assert second.metadata == {}

    with pytest.raises(TypeError):
        PaymentRequest(
            "payment",
            "business",
            "case",
            1.1,
            "USD",
            PaymentType.DEPOSIT,
            PaymentStatus.READY,
            NOW,
            NOW,
            NOW + timedelta(hours=1),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        BookingRequest(
            "business",
            "case",
            "lead",
            "service",
            NOW.replace(tzinfo=None),
            NOW + timedelta(days=1),
        )


def test_get_proposed_slots_returns_stored_slots_while_awaiting_selection() -> None:
    # Regression coverage for the public-widget slot-picker (GET .../commercial
    # proposed_slots, see ConversationService.get_commercial): this is a pure
    # read of conversation.metadata (NOT case.metadata -- that's a distinct,
    # never-written-to field; see the production bug this guards against
    # below), no persistence involved.
    slot_payload = {
        "slot_id": "slot-1",
        "start_at": (NOW + timedelta(hours=1)).isoformat(),
        "end_at": (NOW + timedelta(hours=2)).isoformat(),
        "timezone": "UTC",
        "capacity": 1,
    }
    conversation_metadata = {
        "commercial": {
            "mode": "awaiting_slot",
            "slots": [slot_payload],
            "slots_expires_at": (NOW + timedelta(minutes=30)).isoformat(),
        }
    }
    slots = CommercialWorkflowService().get_proposed_slots(
        conversation_metadata, occurred_at=NOW
    )
    assert [slot.slot_id for slot in slots] == ["slot-1"]


def test_get_proposed_slots_empty_once_expired_or_out_of_slot_mode() -> None:
    slot_payload = {
        "slot_id": "slot-1",
        "start_at": (NOW + timedelta(hours=1)).isoformat(),
        "end_at": (NOW + timedelta(hours=2)).isoformat(),
        "timezone": "UTC",
        "capacity": 1,
    }
    service = CommercialWorkflowService()

    expired = {
        "commercial": {
            "mode": "awaiting_slot",
            "slots": [slot_payload],
            "slots_expires_at": (NOW - timedelta(minutes=1)).isoformat(),
        }
    }
    assert service.get_proposed_slots(expired, occurred_at=NOW) == ()

    booked = {
        "commercial": {"mode": "booked"},
    }
    assert service.get_proposed_slots(booked, occurred_at=NOW) == ()

    no_metadata: dict = {}
    assert service.get_proposed_slots(no_metadata, occurred_at=NOW) == ()


def test_get_proposed_slots_ignores_case_metadata() -> None:
    # Regression test for a real production bug: get_proposed_slots used to
    # read from `case.metadata["commercial"]`, but `initialize()`/
    # `_propose_slots()` only ever write slot proposals into
    # `conversation.metadata["commercial"]` (via `_commercial_metadata()`,
    # always called with the conversation's metadata dict). Because nothing
    # in this codebase ever writes "commercial" into a case's own metadata,
    # the old signature made the widget's slot-picker permanently empty even
    # though the AI's chat reply already listed concrete appointment times.
    # A case-shaped mapping (even one that happens to carry a "commercial"
    # key) must never satisfy this read -- only conversation metadata does.
    slot_payload = {
        "slot_id": "slot-1",
        "start_at": (NOW + timedelta(hours=1)).isoformat(),
        "end_at": (NOW + timedelta(hours=2)).isoformat(),
        "timezone": "UTC",
        "capacity": 1,
    }
    real_conversation_metadata = {"unresolved_items": [], "current_state": "QUALIFIED"}
    slots = CommercialWorkflowService().get_proposed_slots(
        real_conversation_metadata, occurred_at=NOW
    )
    assert slots == ()
    # And the correct source -- conversation metadata carrying the
    # commercial dict written by _propose_slots -- does return them.
    real_conversation_metadata["commercial"] = {
        "mode": "awaiting_slot",
        "slots": [slot_payload],
        "slots_expires_at": (NOW + timedelta(minutes=30)).isoformat(),
    }
    slots = CommercialWorkflowService().get_proposed_slots(
        real_conversation_metadata, occurred_at=NOW
    )
    assert [slot.slot_id for slot in slots] == ["slot-1"]


def test_quote_accept_phrases_and_conditions(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "equipment-replacement")
    interpreter = DeterministicQuoteReplyInterpreter()
    assert interpreter.interpret("sounds good, lets do it").decision == "accept"
    assert interpreter.interpret("works for me").decision == "accept"
    assert interpreter.interpret("no thanks").decision == "decline"
    assert interpreter.interpret("not right now").decision == "unclear"
    assert interpreter.interpret("only if it's under 200").decision == "unclear"
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(uow, case, dna, metadata, "1", occurred_at=NOW)
        response = service.handle_message(
            uow, case, dna, metadata, "sounds good, lets do it", occurred_at=NOW
        )
        assert response.reason == "quote_accepted"
        uow.commit()
    engine.dispose()


def test_option_two_please_books_second_slot(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        first = service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        assert first.reason == "booking_slots_proposed"
        response = service.handle_message(
            uow, case, dna, metadata, "Option 2 please", occurred_at=NOW
        )
        assert response.reason == "booking_confirmed"
        assert case.current_state is ProcessState.WON
        uow.commit()
    engine.dispose()


def test_remote_slots_use_customer_timezone_without_changing_availability(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    dna["service_areas"] = [{"id": "metro", "type": "remote", "values": ["everywhere"]}]
    service = CommercialWorkflowService()
    remote_meta: dict = {"customer_timezone": "America/Los_Angeles"}
    onsite_meta: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        onsite = service.initialize(uow, case, load_dna(), onsite_meta, occurred_at=NOW)
        remote = service.initialize(uow, case, dna, remote_meta, occurred_at=NOW)
        uow.commit()
    remote_ids = [slot["slot_id"] for slot in remote_meta["commercial"]["slots"]]
    onsite_ids = [slot["slot_id"] for slot in onsite_meta["commercial"]["slots"]]
    assert remote_ids == onsite_ids
    assert "PDT" in remote.message_text or "PST" in remote.message_text
    assert "CDT" in onsite.message_text or "CST" in onsite.message_text
    engine.dispose()
