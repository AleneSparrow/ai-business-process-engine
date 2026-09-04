"""Real PostgreSQL commercial persistence and concurrency proofs."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.domain.commercial import QuoteStatus
from src.domain.events import EventType
from src.domain.models import Lead, ProcessCase
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.commercial_service import CommercialWorkflowService
from src.persistence.errors import StaleQuoteError
from src.persistence.sqlalchemy_models import BookingRow, PaymentRequestRow, QuoteRow
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


pytestmark = pytest.mark.postgresql
ROOT = Path(__file__).parents[2]
UTC = timezone.utc


@pytest.fixture(scope="module")
def commercial_pg_factory():
    url = os.getenv("TEST_DATABASE_URL")
    if not url or not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL")
    engine = create_database_engine(url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    yield factory
    engine.dispose()


def seed_cases(factory, service_ids: tuple[str, ...]) -> tuple[str, dict, tuple[str, ...]]:
    dna = json.loads((ROOT / "config" / "business_dna.example.json").read_text())
    business_id = f"commercial-{uuid4()}"
    dna["business"]["id"] = business_id
    now = datetime.now(UTC)
    cases: list[ProcessCase] = []
    with factory() as uow:
        uow.businesses.add(Business(business_id, business_id, now, now))
        uow.business_dna.add_version(business_id, dna)
        for index, service_id in enumerate(service_ids):
            lead = Lead(
                f"lead-{uuid4()}",
                f"Customer {index}",
                None,
                f"+1555{uuid4().int % 10_000_000:07d}",
                {"service_requested": service_id, "customer_location": "60601"},
            )
            case = ProcessCase(
                f"case-{uuid4()}",
                business_id,
                lead,
                ProcessState.QUALIFIED,
                now,
                now,
            )
            uow.leads.add(business_id, lead, now)
            uow.cases.add(case)
            cases.append(case)
        uow.commit()
    return business_id, dna, tuple(case.case_id for case in cases)


def test_two_customers_cannot_take_same_capacity_one_slot(commercial_pg_factory) -> None:
    business_id, dna, case_ids = seed_cases(
        commercial_pg_factory, ("diagnostic-visit", "diagnostic-visit")
    )
    service = CommercialWorkflowService()
    now = datetime.now(UTC)
    metadata = [{}, {}]
    for index, case_id in enumerate(case_ids):
        with commercial_pg_factory() as uow:
            case = uow.cases.get(business_id, case_id)
            service.initialize(uow, case, dna, metadata[index], occurred_at=now)
            uow.commit()
    assert metadata[0]["commercial"]["slots"][0] == metadata[1]["commercial"]["slots"][0]
    barrier = Barrier(2)

    def select_last_slot(index: int):
        with commercial_pg_factory() as uow:
            case = uow.cases.get(business_id, case_ids[index])
            barrier.wait(timeout=10)
            response = service.handle_message(
                uow, case, dna, metadata[index], "1", occurred_at=now
            )
            uow.commit()
            return response

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(select_last_slot, (0, 1)))

    assert sum(result.current_state == ProcessState.WON.value for result in results) == 1
    assert sum(result.reason == "booking_slots_proposed" for result in results) == 1
    winner_index = next(
        index
        for index, result in enumerate(results)
        if result.current_state == ProcessState.WON.value
    )
    with commercial_pg_factory() as uow:
        winner_case = uow.cases.get(business_id, case_ids[winner_index])
        duplicate = service.handle_message(
            uow,
            winner_case,
            dna,
            metadata[winner_index],
            "1",
            occurred_at=now,
        )
            uow.commit()
        assert duplicate.current_state == ProcessState.WON.value
        assert duplicate.reason in {"commercial_won", "awaiting_payment_confirmation"}
    other_business, _, _ = seed_cases(commercial_pg_factory, ())
    with commercial_pg_factory() as uow:
        assert uow.session.scalar(select(func.count()).select_from(BookingRow).where(
            BookingRow.business_id == business_id
        )) == 1
        events = tuple(
            event
            for case_id in case_ids
            for event in uow.events.list_for_case(business_id, case_id)
        )
        assert sum(event.event_type == EventType.BOOKING_CREATED for event in events) == 1
        booking = uow.session.scalar(select(BookingRow).where(
            BookingRow.business_id == business_id
        ))
        assert booking is not None
        assert uow.bookings.get(other_business, booking.id) is None


def test_simultaneous_duplicate_booking_converges_on_one_booking(
    commercial_pg_factory,
) -> None:
    business_id, dna, (case_id,) = seed_cases(
        commercial_pg_factory, ("diagnostic-visit",)
    )
    service = CommercialWorkflowService()
    now = datetime.now(UTC)
    metadata: dict = {}
    with commercial_pg_factory() as uow:
        case = uow.cases.get(business_id, case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=now)
        uow.commit()
    barrier = Barrier(2)

    def select_same_booking():
        with commercial_pg_factory() as uow:
            case = uow.cases.get(business_id, case_id)
            barrier.wait(timeout=10)
            result = service.handle_message(
                uow, case, dna, metadata, "1", occurred_at=now
            )
            uow.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: select_same_booking(), range(2)))

    assert {result.reason for result in results} == {
        "booking_confirmed",
        "booking_duplicate",
    }
    assert {result.current_state for result in results} == {ProcessState.WON.value}
    with commercial_pg_factory() as uow:
        assert uow.session.scalar(select(func.count()).select_from(BookingRow).where(
            BookingRow.business_id == business_id
        )) == 1
        events = uow.events.list_for_case(business_id, case_id)
        assert sum(event.event_type == EventType.BOOKING_CREATED for event in events) == 1


def test_simultaneous_quote_acceptance_has_one_effect_and_payment(
    commercial_pg_factory,
) -> None:
    business_id, dna, (case_id,) = seed_cases(
        commercial_pg_factory, ("equipment-replacement",)
    )
    service = CommercialWorkflowService()
    now = datetime.now(UTC)
    metadata: dict = {}
    with commercial_pg_factory() as uow:
        case = uow.cases.get(business_id, case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=now)
        service.handle_message(uow, case, dna, metadata, "2", occurred_at=now)
        uow.commit()
    barrier = Barrier(2)

    def accept_quote():
        with commercial_pg_factory() as uow:
            case = uow.cases.get(business_id, case_id)
            barrier.wait(timeout=10)
            result = service.handle_message(
                uow, case, dna, metadata, "I accept", occurred_at=now
            )
            uow.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: accept_quote(), range(2)))

    assert {result.reason for result in outcomes} == {
        "quote_accepted",
        "quote_acceptance_duplicate",
    }
    other_business, _, _ = seed_cases(commercial_pg_factory, ())
    with commercial_pg_factory() as uow:
        case = uow.cases.get(business_id, case_id)
        quote = uow.quotes.get_for_case(business_id, case_id)
        events = uow.events.list_for_case(business_id, case_id)
        assert case.current_state is ProcessState.WON
        assert quote.status is QuoteStatus.ACCEPTED
        assert uow.session.scalar(select(func.count()).select_from(PaymentRequestRow).where(
            PaymentRequestRow.business_id == business_id
        )) == 1
        assert sum(event.event_type == EventType.QUOTE_ACCEPTED for event in events) == 1
        assert sum(event.event_type == EventType.PAYMENT_REQUEST_CREATED for event in events) == 1
        payment = uow.session.scalar(select(PaymentRequestRow).where(
            PaymentRequestRow.business_id == business_id
        ))
        assert uow.quotes.get(other_business, quote.quote_id) is None
        assert uow.payment_requests.get(other_business, payment.id) is None


def test_stale_quote_update_is_rejected(commercial_pg_factory) -> None:
    business_id, dna, (case_id,) = seed_cases(
        commercial_pg_factory, ("equipment-replacement",)
    )
    service = CommercialWorkflowService()
    now = datetime.now(UTC)
    metadata: dict = {}
    with commercial_pg_factory() as uow:
        case = uow.cases.get(business_id, case_id)
        service.initialize(uow, case, dna, metadata, occurred_at=now)
        service.handle_message(uow, case, dna, metadata, "1", occurred_at=now)
        uow.commit()

    with commercial_pg_factory() as first, commercial_pg_factory() as second:
        first_quote = first.quotes.get_for_case(business_id, case_id)
        second_quote = second.quotes.get_for_case(business_id, case_id)
        first_expected = first_quote.version
        first_quote.change_status(QuoteStatus.REJECTED, now)
        first.quotes.save(first_quote, first_expected)
        first.commit()
        second_expected = second_quote.version
        second_quote.change_status(QuoteStatus.ACCEPTED, now)
        with pytest.raises(StaleQuoteError):
            second.quotes.save(second_quote, second_expected)


def test_booking_failure_rolls_back_all_commercial_effects_and_can_retry(
    commercial_pg_factory,
) -> None:
    business_id, dna, (case_id,) = seed_cases(
        commercial_pg_factory, ("diagnostic-visit",)
    )
    broken_dna = json.loads(json.dumps(dna))
    broken_dna["payment"]["deposit"] = {
        "required": True,
        "type": "fixed",
        "percentage": None,
        "fixed_amount": "500.00",
    }
    service = CommercialWorkflowService()
    now = datetime.now(UTC)
    metadata: dict = {}
    with commercial_pg_factory() as uow:
        case = uow.cases.get(business_id, case_id)
        service.initialize(uow, case, broken_dna, metadata, occurred_at=now)
        uow.commit()
    with pytest.raises(ValueError, match="must not exceed"):
        with commercial_pg_factory() as uow:
            case = uow.cases.get(business_id, case_id)
            service.handle_message(uow, case, broken_dna, metadata, "1", occurred_at=now)
            uow.commit()

    with commercial_pg_factory() as uow:
        case = uow.cases.get(business_id, case_id)
        assert case.current_state is ProcessState.QUALIFIED
        assert uow.session.scalar(select(func.count()).select_from(BookingRow).where(
            BookingRow.business_id == business_id
        )) == 0
        events = uow.events.list_for_case(business_id, case_id)
        assert not any(event.event_type == EventType.BOOKING_CREATED for event in events)

    with commercial_pg_factory() as uow:
        case = uow.cases.get(business_id, case_id)
        result = service.handle_message(uow, case, dna, metadata, "1", occurred_at=now)
        uow.commit()
        assert result.current_state == ProcessState.WON.value
