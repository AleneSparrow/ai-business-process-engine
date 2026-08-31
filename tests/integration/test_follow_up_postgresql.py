"""Real PostgreSQL concurrency proofs for PersistentFollowUpRunner's durable
outbox (see tests/test_follow_up_service.py for the SQLite-backed behavioral
coverage of the same feature -- crash/retry recovery, failed delivery). This
file exercises the one thing that needs a real second connection to prove:
two truly concurrent sweeps claiming the SAME delivery attempt must result
in exactly one Twilio send, never two."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.domain.events import EventType
from src.domain.models import Lead, ProcessCase, ProcessEvent
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.follow_up_service import PersistentFollowUpRunner
from src.persistence.sqlalchemy_models import FollowUpDeliveryAttemptRow
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


pytestmark = pytest.mark.postgresql

_BUSINESS_DNA = {
    "business": {"name": "Acme Home Services"},
    "sales": {"follow_up": {"delays_hours": [24, 72, 168], "maximum_attempts": 3}},
    "customer_information": {
        "field_questions": {"phone": "What is the best number to reach you?"},
    },
}


class ThreadSafeFakeSmsService:
    """Same fake as tests/test_follow_up_service.py's, made safe for two
    real threads sharing it -- never touches the network."""

    def __init__(self) -> None:
        self.configured = True
        self._lock = Lock()
        self.send_calls: list[tuple[str, str, str]] = []
        self._next_sid = 1

    def get_number(self, business_id: str) -> str | None:
        return "+15005550006"

    def send_outbound(self, business_id: str, *, to_number: str, body: str) -> str | None:
        with self._lock:
            self.send_calls.append((business_id, to_number, body))
            sid = f"SM{self._next_sid:032x}"
            self._next_sid += 1
        return sid


@pytest.fixture(scope="module")
def pg_factory():
    url = os.getenv("TEST_DATABASE_URL")
    if not url or not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL")
    engine = create_database_engine(url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    yield factory
    engine.dispose()


def _make_stalled_case(pg_factory, business_id: str, case_id: str, now: datetime) -> None:
    last_activity = now - timedelta(hours=25)
    lead = Lead(f"lead-{case_id}", "Ada", None, "+15551234567", sms_consent=True)
    case = ProcessCase(
        case_id, business_id, lead, current_state=ProcessState.QUALIFYING, created_at=now - timedelta(days=10)
    )
    case.record(ProcessEvent(EventType.LEAD_INTAKE_RECEIVED, occurred_at=last_activity, source="sms"))
    case.record(ProcessEvent(
        EventType.QUALIFICATION_EVALUATED,
        occurred_at=last_activity,
        source="qualification_service",
        payload={"missing_fields": ["phone"], "unanswered_questions": []},
    ))
    dna = {**_BUSINESS_DNA, "business": {**_BUSINESS_DNA["business"], "id": business_id}}
    with pg_factory() as uow:
        uow.businesses.add(Business(business_id, "Acme Home Services", now, now))
        uow.business_dna.add_version(business_id, dna)
        uow.leads.add(business_id, lead, now - timedelta(days=10))
        uow.cases.add(case)
        uow.events.add_many(business_id, case_id, case.event_history)
        uow.commit()


def test_concurrent_sweeps_on_same_case_send_exactly_once(pg_factory) -> None:
    suffix = uuid4().hex
    business_id, case_id = f"pg-follow-up-conflict-{suffix}", f"case-conflict-{suffix}"
    now = datetime.now(timezone.utc)
    _make_stalled_case(pg_factory, business_id, case_id, now)
    sms = ThreadSafeFakeSmsService()
    barrier = Barrier(2)

    def run_sweep():
        runner = PersistentFollowUpRunner(pg_factory, sms)
        barrier.wait(timeout=10)
        return runner._send_one(business_id, case_id, now)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: run_sweep(), range(2)))

    # Exactly one thread actually claimed and sent. The other either backs
    # off, finds the case no longer due, or loses the optimistic case-version
    # race after the first worker commits ("stale"). All four outcomes are
    # safe: none may send a second SMS or create a second attempt.
    assert len(sms.send_calls) == 1
    assert outcomes.count("sent") == 1
    assert set(outcomes) <= {"sent", "already_claimed", "no_longer_due", "stale"}

    with pg_factory() as uow:
        case = uow.cases.get(business_id, case_id)
        attempt_count = uow.session.scalar(
            select(func.count()).select_from(FollowUpDeliveryAttemptRow).where(
                FollowUpDeliveryAttemptRow.business_id == business_id,
                FollowUpDeliveryAttemptRow.case_id == case_id,
            )
        )
        events = uow.events.list_for_case(business_id, case_id)
    assert case.metadata["follow_up_attempts_sent"] == 1
    assert attempt_count == 1  # one delivery-attempt row, not two
    assert sum(event.event_type == EventType.FOLLOW_UP_SENT for event in events) == 1


def test_claim_attempt_takeover_is_exclusive_under_concurrency(pg_factory) -> None:
    """Two callers racing to take over the same abandoned (long-PENDING)
    attempt must not both win the takeover."""
    suffix = uuid4().hex
    business_id, case_id = f"pg-follow-up-takeover-{suffix}", f"case-takeover-{suffix}"
    now = datetime.now(timezone.utc)
    _make_stalled_case(pg_factory, business_id, case_id, now)

    with pg_factory() as uow:
        uow.follow_up_deliveries.claim_attempt(business_id, case_id, 1, message_text="hi", now=now)
        uow.commit()

    much_later = now + timedelta(minutes=10)
    barrier = Barrier(2)

    def race_takeover():
        with pg_factory() as uow:
            barrier.wait(timeout=10)
            _attempt, owns = uow.follow_up_deliveries.claim_attempt(
                business_id, case_id, 1, message_text="takeover attempt", now=much_later
            )
            uow.commit()
            return owns

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: race_takeover(), range(2)))

    assert results.count(True) == 1  # exactly one caller won the takeover
