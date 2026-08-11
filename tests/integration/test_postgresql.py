"""PostgreSQL-only transaction and concurrency tests.

Set TEST_DATABASE_URL to a dedicated, migrated PostgreSQL database to enable.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.domain.events import EventType
from src.domain.models import DecisionType, Lead, ProcessCase, ProcessEvent, utc_now
from src.domain.qualification import IncomingMessage, IntentResult
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.engine.decision_router import DecisionRequest
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.engine.process_engine import ProcessEngine
from src.engine.question_generator import DeterministicQuestionGenerator
from src.persistence.errors import IdempotencyCollisionError, StaleCaseError
from src.persistence.lead_intake import PersistentLeadIntakeService
from src.persistence.sqlalchemy_models import LeadRow, ProcessCaseRow, ProcessedMessageRow
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


pytestmark = pytest.mark.postgresql
ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def pg_factory():
    url = os.getenv("TEST_DATABASE_URL")
    if not url or not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL")
    engine = create_database_engine(url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    yield factory
    engine.dispose()


def seed(factory) -> str:
    business_id = f"concurrency-{uuid4()}"
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        configuration = json.load(file)
    configuration["business"]["id"] = business_id
    now = utc_now()
    with factory() as uow:
        uow.businesses.add(Business(business_id, business_id, now, now))
        uow.business_dna.add_version(business_id, configuration)
        uow.commit()
    return business_id


def test_concurrent_duplicate_intake_has_one_logical_effect(pg_factory) -> None:
    business_id = seed(pg_factory)
    external_id = str(uuid4())
    intent = IntentResult(
        service_requested="diagnostic-visit", customer_location="60601", confidence=0.95
    )
    service = PersistentLeadIntakeService(
        pg_factory,
        DeterministicIntentExtractor({external_id: intent}),
        DeterministicQuestionGenerator(),
    )
    message = IncomingMessage(
        business_id=business_id,
        channel="sms",
        external_message_id=external_id,
        customer_name="Concurrent Customer",
        phone=f"+1{str(uuid4().int)[:10]}",
        raw_text="diagnostic visit in 60601",
        timestamp=datetime.now(timezone.utc),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        start = Barrier(2)

        def receive_concurrently(value: IncomingMessage):
            start.wait(timeout=10)
            return service.receive(value)

        results = list(executor.map(receive_concurrently, (message, message)))

    logical_results = {
        (
            result.case_id,
            result.lead_id,
            result.current_state,
            result.qualification,
            result.response,
            result.case_created,
        )
        for result in results
    }
    assert len(logical_results) == 1
    assert sum(result.duplicate for result in results) == 1
    with pg_factory() as uow:
        events = uow.events.list_for_case(business_id, results[0].case_id)
        for event_type in (
            EventType.LEAD_INTAKE_RECEIVED,
            EventType.INTENT_EXTRACTED,
            EventType.QUALIFICATION_EVALUATED,
        ):
            assert sum(event.event_type == event_type for event in events) == 1
        assert uow.session.scalar(
            select(func.count()).select_from(LeadRow).where(LeadRow.business_id == business_id)
        ) == 1
        assert uow.session.scalar(
            select(func.count()).select_from(ProcessCaseRow).where(
                ProcessCaseRow.business_id == business_id
            )
        ) == 1
        assert uow.session.scalar(
            select(func.count()).select_from(ProcessedMessageRow).where(
                ProcessedMessageRow.business_id == business_id
            )
        ) == 1


def test_concurrent_same_identity_different_fingerprint_is_collision(pg_factory) -> None:
    business_id = seed(pg_factory)
    external_id = str(uuid4())
    intent = IntentResult(
        service_requested="diagnostic-visit", customer_location="60601", confidence=0.95
    )
    service = PersistentLeadIntakeService(
        pg_factory,
        DeterministicIntentExtractor({external_id: intent}),
        DeterministicQuestionGenerator(),
    )
    base = {
        "business_id": business_id,
        "channel": "sms",
        "external_message_id": external_id,
        "customer_name": "Collision Customer",
        "phone": f"+1{str(uuid4().int)[:10]}",
        "timestamp": datetime.now(timezone.utc),
    }
    first = IncomingMessage(raw_text="diagnostic visit in 60601", **base)
    second = IncomingMessage(raw_text="different content for the same identity", **base)
    start = Barrier(2)

    def receive_or_error(value: IncomingMessage):
        start.wait(timeout=10)
        try:
            return service.receive(value)
        except IdempotencyCollisionError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(receive_or_error, (first, second)))

    assert sum(isinstance(outcome, IdempotencyCollisionError) for outcome in outcomes) == 1
    successful = next(outcome for outcome in outcomes if not isinstance(outcome, Exception))
    with pg_factory() as uow:
        events = uow.events.list_for_case(business_id, successful.case_id)
        assert sum(event.event_type == EventType.LEAD_INTAKE_RECEIVED for event in events) == 1
        assert uow.session.scalar(
            select(func.count()).select_from(LeadRow).where(LeadRow.business_id == business_id)
        ) == 1


class FailingExtractor:
    def extract(self, message: IncomingMessage, business_dna: dict) -> IntentResult:
        raise RuntimeError("simulated worker failure")


def test_failed_claim_transaction_can_be_retried(pg_factory) -> None:
    business_id = seed(pg_factory)
    external_id = str(uuid4())
    message = IncomingMessage(
        business_id=business_id,
        channel="sms",
        external_message_id=external_id,
        customer_name="Retry Customer",
        phone=f"+1{str(uuid4().int)[:10]}",
        raw_text="diagnostic visit in 60601",
        timestamp=datetime.now(timezone.utc),
    )
    failing = PersistentLeadIntakeService(
        pg_factory, FailingExtractor(), DeterministicQuestionGenerator()
    )
    with pytest.raises(RuntimeError, match="simulated worker failure"):
        failing.receive(message)

    retry = PersistentLeadIntakeService(
        pg_factory,
        DeterministicIntentExtractor({external_id: IntentResult(
            service_requested="diagnostic-visit", customer_location="60601", confidence=0.95
        )}),
        DeterministicQuestionGenerator(),
    )
    result = retry.receive(message)
    assert result.current_state is ProcessState.QUALIFIED
    with pg_factory() as uow:
        events = uow.events.list_for_case(business_id, result.case_id)
        assert sum(event.event_type == EventType.LEAD_INTAKE_RECEIVED for event in events) == 1


def test_two_concurrent_case_updates_detect_one_stale_writer(pg_factory) -> None:
    business_id = seed(pg_factory)
    lead = Lead(str(uuid4()), "Concurrent Customer")
    case = ProcessCase(str(uuid4()), business_id, lead)
    with pg_factory() as uow:
        uow.leads.add(business_id, lead, case.created_at)
        uow.cases.add(case)
        uow.commit()

    barrier = Barrier(2)

    def compete(target: ProcessState, event_id: str) -> str:
        try:
            with pg_factory() as uow:
                loaded = uow.cases.get(business_id, case.case_id)
                assert loaded is not None
                barrier.wait(timeout=10)
                ProcessEngine().receive(
                    loaded,
                    ProcessEvent("COMPETING_TRANSITION", event_id=event_id),
                    DecisionRequest(DecisionType.RULE, target),
                )
                uow.cases.save(loaded, expected_version=0)
                uow.events.add_many(business_id, loaded.case_id, loaded.event_history)
                uow.commit()
                return "saved"
        except StaleCaseError:
            return "stale"

    first_id = f"first-{uuid4()}"
    second_id = f"second-{uuid4()}"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda args: compete(*args),
            ((ProcessState.CONTACTED, first_id), (ProcessState.LOST, second_id)),
        ))

    assert sorted(results) == ["saved", "stale"]
    with pg_factory() as uow:
        persisted = uow.cases.get(business_id, case.case_id)
        assert persisted is not None and persisted.version == 1
        event_ids = {event.event_id for event in persisted.event_history}
        assert len({first_id, second_id}.intersection(event_ids)) == 1
