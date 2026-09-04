"""Post-sale lifecycle: WON → PAID → COMPLETED → REVIEW_REQUESTED, plus booking win."""

from datetime import timedelta

from sqlalchemy import select

import pytest

from src.domain.commercial import BookingStatus, PaymentStatus
from src.domain.events import EventType
from src.domain.lifecycle import LifecycleAction, actions_for_state
from src.domain.models import DecisionType, ProcessEvent
from src.domain.states import ProcessState
from src.engine.decision_router import DecisionRequest
from src.persistence.commercial_service import CommercialWorkflowService
from src.persistence.errors import InvalidLifecycleActionError
from src.persistence.lifecycle_sweep import LifecycleSweep
from src.persistence.sqlalchemy_models import BookingRow, PaymentRequestRow

from tests.test_commercial import NOW, make_factory


def test_booking_confirmation_closes_the_commercial_win(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        response = service.handle_message(
            uow, case, dna, metadata, "The second option works", occurred_at=NOW
        )
        uow.commit()
        assert response.reason == "booking_confirmed"
        assert case.current_state is ProcessState.WON
        assert actions_for_state(case.current_state) == (
            LifecycleAction.RECORD_PAYMENT,
            LifecycleAction.MARK_COMPLETED,
        )
    engine.dispose()


def test_staff_can_record_payment_complete_work_and_request_review(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(
            uow, case, dna, metadata, "The second option works", occurred_at=NOW
        )
        uow.commit()

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        paid = service.record_customer_payment(
            uow, case, occurred_at=NOW, recorded_by="owner@example.com"
        )
        assert paid.reason == "payment_recorded"
        assert case.current_state is ProcessState.PAID
        payment = uow.session.scalar(select(PaymentRequestRow))
        assert payment.status == PaymentStatus.PAID.value
        uow.commit()

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        done = service.mark_service_completed(
            uow, case, occurred_at=NOW + timedelta(hours=2), recorded_by="owner@example.com"
        )
        assert done.reason == "service_completed"
        assert case.current_state is ProcessState.COMPLETED
        booking = uow.session.scalar(select(BookingRow))
        assert booking.status == BookingStatus.COMPLETED.value
        uow.commit()

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        review = service.request_review(
            uow,
            case,
            dna,
            occurred_at=NOW + timedelta(hours=3),
            recorded_by="owner@example.com",
        )
        assert review.reason == "review_requested"
        assert case.current_state is ProcessState.REVIEW_REQUESTED
        assert "review" in review.message_text.casefold()
        uow.commit()
    engine.dispose()


def test_mark_completed_from_won_requires_settled_payment_when_one_exists(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(
            uow, case, dna, metadata, "The second option works", occurred_at=NOW
        )
        with pytest.raises(InvalidLifecycleActionError, match="Record payment"):
            service.mark_service_completed(
                uow, case, occurred_at=NOW, recorded_by="owner@example.com"
            )
        uow.commit()
    engine.dispose()


def test_quote_accept_stays_won_until_staff_records_payment(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "equipment-replacement")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(uow, case, dna, metadata, "2", occurred_at=NOW)
        response = service.handle_message(
            uow, case, dna, metadata, "Yes, let's do it", occurred_at=NOW
        )
        assert response.reason == "quote_accepted"
        assert case.current_state is ProcessState.WON
        payment = uow.session.scalar(select(PaymentRequestRow))
        assert payment.status == PaymentStatus.READY.value
        uow.commit()

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.record_customer_payment(
            uow, case, occurred_at=NOW, recorded_by="owner@example.com"
        )
        assert case.current_state is ProcessState.PAID
        uow.commit()
    engine.dispose()


def test_direct_next_step_is_won_only_after_staff_verification(tmp_path) -> None:
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
        assert case.current_state is ProcessState.QUALIFIED
        confirmed = service.confirm_direct_next_step(
            uow,
            case,
            metadata,
            occurred_at=NOW,
            recorded_by="owner@example.com",
        )
        assert confirmed.reason == "direct_next_step_confirmed"
        assert case.current_state is ProcessState.WON
        uow.commit()
    engine.dispose()


def test_resolving_high_value_booking_approval_closes_to_won(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    dna["payment"]["human_approval_above"] = "1.00"
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        response = service.handle_message(
            uow, case, dna, metadata, "1", occurred_at=NOW
        )
        assert response.requires_human is True
        assert case.current_state is ProcessState.NEEDS_HUMAN
        assert case.pending_transition is ProcessState.FOLLOW_UP
        uow.commit()

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        expected = case.version
        existing_event_count = len(case.event_history)
        event = ProcessEvent(
            EventType.TRIGGER_RECEIVED,
            occurred_at=NOW,
            source="test",
            payload={"action": "resolve"},
        )
        service.process_engine.receive(
            case,
            event,
            DecisionRequest(
                DecisionType.HUMAN, ProcessState.FOLLOW_UP, approved_by="owner@example.com"
            ),
        )
        uow.cases.save(case, expected)
        uow.events.add_many(
            case.business_id, case.case_id, case.event_history[existing_event_count:]
        )
        assert case.current_state is ProcessState.FOLLOW_UP
        assert service.complete_win_if_ready(uow, case, occurred_at=NOW) is True
        assert case.current_state is ProcessState.WON
        uow.commit()
    engine.dispose()


def test_lifecycle_sweep_waits_for_payment_then_completes_and_asks_for_review(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(
            uow, case, dna, metadata, "The second option works", occurred_at=NOW
        )
        uow.commit()

    with factory() as uow:
        booking = uow.bookings.get_for_case(dna["business"]["id"], case_id)
        after_visit = booking.end_at + timedelta(minutes=1)
        uow.commit()

    skipped = LifecycleSweep(factory).run(after_visit)
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        assert case.current_state is ProcessState.WON
        uow.commit()
    assert skipped["completed"] == 0
    assert skipped["reviews_requested"] == 0

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.record_customer_payment(
            uow, case, occurred_at=after_visit, recorded_by="owner@example.com"
        )
        uow.commit()

    advanced = LifecycleSweep(factory).run(after_visit)
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        booking = uow.bookings.get_for_case(dna["business"]["id"], case_id)
        assert case.current_state is ProcessState.REVIEW_REQUESTED
        assert booking.status is BookingStatus.COMPLETED
        uow.commit()
    assert advanced["completed"] == 1
    assert advanced["reviews_requested"] == 1
    engine.dispose()


def test_customer_confirms_payment_in_chat(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(
            uow, case, dna, metadata, "The second option works", occurred_at=NOW
        )
        uow.commit()

    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        response = service.handle_message(
            uow, case, dna, metadata, "I paid just now", occurred_at=NOW
        )
        assert response.reason == "payment_recorded"
        assert case.current_state is ProcessState.PAID
        uow.commit()
    engine.dispose()


def test_customer_says_work_went_well_closes_the_cycle(tmp_path) -> None:
    engine, factory, dna, case_id = make_factory(tmp_path, "diagnostic-visit")
    service = CommercialWorkflowService()
    metadata: dict = {}
    with factory() as uow:
        case = uow.cases.get(dna["business"]["id"], case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=NOW)
        service.handle_message(
            uow, case, dna, metadata, "The second option works", occurred_at=NOW
        )
        service.record_customer_payment(
            uow, case, occurred_at=NOW, recorded_by="customer"
        )
        response = service.handle_message(
            uow, case, dna, metadata, "The visit went well", occurred_at=NOW
        )
        assert response.reason == "review_requested"
        assert case.current_state is ProcessState.REVIEW_REQUESTED
        uow.commit()
    engine.dispose()
