"""PostgreSQL-only transaction and concurrency tests.

Set TEST_DATABASE_URL to a dedicated, migrated PostgreSQL database to enable.
"""

import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.domain.events import EventType
from src.domain.models import DecisionType, Lead, ProcessCase, ProcessEvent, utc_now
from src.domain.qualification import IncomingMessage, IntentResult
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.engine.decision_router import DecisionRequest
from src.engine.customer_response_generator import DeterministicCustomerResponseGenerator
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.engine.process_engine import ProcessEngine
from src.engine.question_generator import DeterministicQuestionGenerator
from src.persistence.conversation_service import ConversationService
from src.persistence.errors import (
    ConversationTokenError,
    IdempotencyCollisionError,
    StaleCaseError,
)
from src.persistence.lead_intake import PersistentLeadIntakeService
from src.persistence.sqlalchemy_models import (
    ConversationMessageRow,
    ConversationRow,
    LeadRow,
    ProcessCaseRow,
    ProcessedMessageRow,
)
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


class CountingDeterministicExtractor:
    def __init__(self) -> None:
        self.delegate = DeterministicIntentExtractor()
        self.calls = 0
        self.lock = Lock()

    def extract(self, message: IncomingMessage, business_dna: dict) -> IntentResult:
        with self.lock:
            self.calls += 1
        return self.delegate.extract(message, business_dna)


def make_conversation_service(pg_factory, extractor=None) -> ConversationService:
    return ConversationService(
        pg_factory,
        extractor or DeterministicIntentExtractor(),
        DeterministicQuestionGenerator(),
        DeterministicCustomerResponseGenerator(),
    )


def test_postgresql_conversation_persistence_and_tenant_isolation(pg_factory) -> None:
    business_id = seed(pg_factory)
    other_business_id = seed(pg_factory)
    service = make_conversation_service(pg_factory)

    created = service.create(
        business_id,
        message_text="I need AC help. Phone +1 312 555 0100. My name is Ada",
        external_message_id="pg-conversation-first",
    )
    restored = service.get(business_id, created.conversation_token)

    assert restored.internal_conversation_id == created.internal_conversation_id
    assert len(restored.messages) == 2
    with pytest.raises(ConversationTokenError):
        service.get(other_business_id, created.conversation_token)
    with pg_factory() as uow:
        assert uow.session.scalar(
            select(func.count()).select_from(ConversationRow).where(
                ConversationRow.business_id == business_id
            )
        ) == 1
        assert uow.session.scalar(
            select(func.count()).select_from(ConversationMessageRow).where(
                ConversationMessageRow.business_id == business_id
            )
        ) == 2


def test_concurrent_duplicate_conversation_message_has_one_effect(pg_factory) -> None:
    business_id = seed(pg_factory)
    extractor = CountingDeterministicExtractor()
    service = make_conversation_service(pg_factory, extractor)
    created = service.create(business_id)
    start = Barrier(2)

    def send_duplicate():
        start.wait(timeout=10)
        return service.send_message(
            business_id,
            created.conversation_token,
            message_text="I need AC help",
            external_message_id="duplicate-browser-message",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: send_duplicate(), range(2)))

    assert sum(result.duplicate for result in results) == 1
    assert extractor.calls == 1
    with pg_factory() as uow:
        conversation = uow.session.scalar(select(ConversationRow).where(
            ConversationRow.id == created.internal_conversation_id,
            ConversationRow.business_id == business_id,
        ))
        assert conversation is not None and conversation.case_id is not None
        assert uow.session.scalar(select(func.count()).select_from(ConversationMessageRow).where(
            ConversationMessageRow.business_id == business_id,
            ConversationMessageRow.conversation_id == created.internal_conversation_id,
        )) == 2
        events = uow.events.list_for_case(business_id, conversation.case_id)
        assert sum(event.event_type == EventType.LEAD_INTAKE_RECEIVED for event in events) == 1


def test_concurrent_duplicate_conversation_create_converges(pg_factory) -> None:
    business_id = seed(pg_factory)
    extractor = CountingDeterministicExtractor()
    service = make_conversation_service(pg_factory, extractor)
    token = secrets.token_urlsafe(32)
    start = Barrier(2)

    def create_duplicate():
        start.wait(timeout=10)
        return service.create(
            business_id,
            message_text="I need AC help",
            external_message_id="duplicate-create-message",
            conversation_token=token,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_duplicate(), range(2)))

    assert len({result.internal_conversation_id for result in results}) == 1
    assert sum(result.duplicate for result in results) == 1
    assert extractor.calls == 1
    with pg_factory() as uow:
        assert uow.session.scalar(select(func.count()).select_from(ConversationRow).where(
            ConversationRow.business_id == business_id
        )) == 1
        assert uow.session.scalar(select(func.count()).select_from(ConversationMessageRow).where(
            ConversationMessageRow.business_id == business_id
        )) == 2


def test_concurrent_distinct_followups_are_ordered_and_consistent(pg_factory) -> None:
    business_id = seed(pg_factory)
    service = make_conversation_service(pg_factory)
    created = service.create(
        business_id,
        message_text="I need AC help. My name is Ada",
        external_message_id="ordered-first",
    )
    start = Barrier(2)
    followups = (
        ("60601", "ordered-zip"),
        ("My phone is +1 312 555 0198", "ordered-phone"),
    )

    def send_followup(value: tuple[str, str]):
        start.wait(timeout=10)
        return service.send_message(
            business_id,
            created.conversation_token,
            message_text=value[0],
            external_message_id=value[1],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(send_followup, followups))

    restored = service.get(business_id, created.conversation_token)
    assert restored.current_state is ProcessState.QUALIFIED
    assert len(restored.messages) == 6
    with pg_factory() as uow:
        rows = tuple(uow.session.scalars(
            select(ConversationMessageRow)
            .where(
                ConversationMessageRow.business_id == business_id,
                ConversationMessageRow.conversation_id == created.internal_conversation_id,
            )
            .order_by(ConversationMessageRow.sequence_number)
        ))
        assert [row.sequence_number for row in rows] == list(range(1, 7))
        conversation = uow.session.scalar(select(ConversationRow).where(
            ConversationRow.business_id == business_id,
            ConversationRow.id == created.internal_conversation_id,
        ))
        assert conversation is not None
        assert conversation.version == 3


def test_concurrent_conversation_collision_is_explicit(pg_factory) -> None:
    business_id = seed(pg_factory)
    service = make_conversation_service(pg_factory)
    created = service.create(business_id)
    start = Barrier(2)

    def send_or_error(text_value: str):
        start.wait(timeout=10)
        try:
            return service.send_message(
                business_id,
                created.conversation_token,
                message_text=text_value,
                external_message_id="same-browser-id",
            )
        except IdempotencyCollisionError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(send_or_error, ("I need AC help", "different text")))

    assert sum(isinstance(outcome, IdempotencyCollisionError) for outcome in outcomes) == 1
    with pg_factory() as uow:
        assert uow.session.scalar(select(func.count()).select_from(ConversationMessageRow).where(
            ConversationMessageRow.business_id == business_id,
            ConversationMessageRow.conversation_id == created.internal_conversation_id,
        )) == 2


def test_concurrent_conversations_cannot_claim_same_contact_identity(pg_factory) -> None:
    business_id = seed(pg_factory)
    service = make_conversation_service(pg_factory)
    phone = f"+1555{uuid4().int % 10_000_000:07d}"
    start = Barrier(2)

    def create_with_same_phone(customer_name: str):
        start.wait(timeout=10)
        return service.create(
            business_id,
            message_text=(
                f"AC diagnostic in 60601. My phone is {phone}. "
                f"My name is {customer_name}"
            ),
            external_message_id=f"same-contact-{customer_name}-{uuid4()}",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create_with_same_phone, ("Ada", "Grace")))

    assert {result.current_state for result in results} == {
        ProcessState.QUALIFIED,
        ProcessState.NEEDS_HUMAN,
    }
    with pg_factory() as uow:
        leads = tuple(uow.session.scalars(
            select(LeadRow).where(LeadRow.business_id == business_id)
        ))
        assert len(leads) == 2
        assert sum(lead.normalized_phone == phone for lead in leads) == 1


def test_rehydrated_process_case_rejects_duplicate_event_against_postgresql(pg_factory) -> None:
    """PostgreSQL counterpart of
    tests/test_persistence.py::test_rehydrated_case_rejects_duplicate_event_id_and_keeps_one_effect
    -- same rehydration-idempotency regression, against the real
    persistence backend production actually runs on."""
    business_id = seed(pg_factory)
    case_id = f"rehydrate-case-{uuid4()}"
    lead = Lead(f"rehydrate-lead-{uuid4()}", "Ada")
    case = ProcessCase(case_id, business_id, lead)
    with pg_factory() as uow:
        uow.leads.add(business_id, lead, case.created_at)
        uow.cases.add(case)
        uow.commit()

    with pg_factory() as uow:
        loaded = uow.cases.get(business_id, case_id)
        assert loaded is not None
        event_id = f"contact-event-{uuid4()}"
        ProcessEngine().receive(
            loaded, ProcessEvent("first_contact", event_id=event_id),
            DecisionRequest(DecisionType.RULE, ProcessState.CONTACTED),
        )
        uow.cases.save(loaded, expected_version=0)
        uow.events.add_many(loaded.business_id, loaded.case_id, loaded.event_history)
        uow.commit()

    with pg_factory() as uow:
        rehydrated = uow.cases.get(business_id, case_id)
        assert rehydrated is not None
        assert rehydrated.has_processed(event_id)

        decision = ProcessEngine().receive(
            rehydrated, ProcessEvent("first_contact", event_id=event_id),
            DecisionRequest(DecisionType.RULE, ProcessState.QUALIFYING),
        )
        assert not decision.approved
        assert rehydrated.current_state is ProcessState.CONTACTED

        uow.cases.save(rehydrated, expected_version=rehydrated.version)
        uow.events.add_many(rehydrated.business_id, rehydrated.case_id, (rehydrated.event_history[-1],))
        uow.commit()

    with pg_factory() as uow:
        final = uow.cases.get(business_id, case_id)
        assert final is not None
        assert final.current_state is ProcessState.CONTACTED
        assert sum(event.event_type == EventType.STATE_CHANGED for event in final.event_history) == 1
        assert sum(event.event_type == EventType.DUPLICATE_IGNORED for event in final.event_history) == 1
