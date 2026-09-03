"""PersistentFollowUpRunner (src/persistence/follow_up_service.py) against a
real (SQLite) unit of work -- the durable-outbox delivery path in
`_send_one`, not the pure decision logic (see tests/test_follow_up.py for
that -- decide_follow_up, missing_information_from_case, the message
generator). No real Twilio call is ever made here: `FakeSmsService` below
stands in for `SmsService`, recording calls instead of touching the network.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.domain.events import EventType
from src.domain.models import Lead, ProcessCase, ProcessEvent, utc_now
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.errors import StaleCaseError
from src.persistence.follow_up_service import PersistentFollowUpRunner
from src.persistence.repositories import DeliveryStatus
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_repositories import SQLAlchemyProcessCaseRepository
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

_BUSINESS_ID = "biz-1"
_CASE_ID = "case-1"

_BUSINESS_DNA = {
    "business": {"id": _BUSINESS_ID, "name": "Acme Home Services"},
    "sales": {"follow_up": {"delays_hours": [24, 72, 168], "maximum_attempts": 3}},
    "customer_information": {
        "field_questions": {"phone": "What is the best number to reach you?"},
    },
}


class FakeSmsService:
    """Stands in for SmsService: never touches the network, records every
    call so tests can assert exactly one (or zero) sends happened."""

    def __init__(self, *, number: str | None = "+15005550006", fail: bool = False) -> None:
        self.configured = True
        self._number = number
        self._fail = fail
        self.send_calls: list[tuple[str, str, str]] = []
        self._next_sid = 1

    def get_number(self, business_id: str) -> str | None:
        return self._number

    def is_suppressed(self, business_id: str, phone_number: str) -> bool:
        return False

    def send_outbound(self, business_id: str, *, to_number: str, body: str) -> str | None:
        self.send_calls.append((business_id, to_number, body))
        if self._fail:
            return None
        sid = f"SM{self._next_sid:032x}"
        self._next_sid += 1
        return sid


@pytest.fixture
def uow_factory(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'follow_up.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    yield SQLAlchemyUnitOfWork.factory_for_engine(engine)
    engine.dispose()


def _make_stalled_case(
    uow_factory,
    *,
    business_id: str = _BUSINESS_ID,
    case_id: str = _CASE_ID,
    last_activity: datetime | None = None,
    provision_sms_number: str | None = None,
) -> None:
    last_activity = last_activity or (NOW - timedelta(hours=25))
    lead = Lead("lead-1", "Ada", None, "+15551234567", sms_consent=True)
    case = ProcessCase(
        case_id, business_id, lead, current_state=ProcessState.QUALIFYING, created_at=NOW - timedelta(days=10)
    )
    case.record(ProcessEvent(EventType.LEAD_INTAKE_RECEIVED, occurred_at=last_activity, source="sms"))
    case.record(ProcessEvent(
        EventType.QUALIFICATION_EVALUATED,
        occurred_at=last_activity,
        source="qualification_service",
        payload={"missing_fields": ["phone"], "unanswered_questions": []},
    ))
    with uow_factory() as uow:
        uow.businesses.add(Business(business_id, "Acme Home Services", NOW, NOW))
        uow.business_dna.add_version(business_id, _BUSINESS_DNA)
        uow.leads.add(business_id, lead, NOW - timedelta(days=10))
        uow.cases.add(case)
        uow.events.add_many(business_id, case_id, case.event_history)
        if provision_sms_number is not None:
            uow.sms_connections.add(business_id, provision_sms_number, "PN_fake_sid", now=NOW)
        uow.commit()


def _events(uow_factory, business_id: str, case_id: str):
    with uow_factory() as uow:
        return uow.events.list_for_case(business_id, case_id)


def _change_case_state(uow_factory, state: ProcessState) -> None:
    with uow_factory() as uow:
        case = uow.cases.get(_BUSINESS_ID, _CASE_ID)
        assert case is not None
        expected_version = case.version
        case._apply_transition(state)
        uow.cases.save(case, expected_version)
        uow.commit()


# --- Happy path -----------------------------------------------------------------------


def test_send_one_sends_and_records_delivery_before_case_update(uow_factory) -> None:
    _make_stalled_case(uow_factory)
    sms = FakeSmsService()
    runner = PersistentFollowUpRunner(uow_factory, sms)

    outcome = runner._send_one(_BUSINESS_ID, _CASE_ID, NOW)

    assert outcome == "sent"
    assert len(sms.send_calls) == 1
    business_id, to_number, _body = sms.send_calls[0]
    assert business_id == _BUSINESS_ID
    assert to_number == "+15551234567"

    with uow_factory() as uow:
        case = uow.cases.get(_BUSINESS_ID, _CASE_ID)
        attempt, _owns = uow.follow_up_deliveries.claim_attempt(
            _BUSINESS_ID, _CASE_ID, 1, message_text="unused", now=NOW
        )
    assert case.metadata["follow_up_attempts_sent"] == 1
    assert attempt.status == DeliveryStatus.SENT
    assert attempt.twilio_sid is not None

    sent_events = [e for e in _events(uow_factory, _BUSINESS_ID, _CASE_ID) if e.event_type == EventType.FOLLOW_UP_SENT]
    assert len(sent_events) == 1
    assert sent_events[0].payload["delivered"] is True
    assert sent_events[0].payload["twilio_sid"] == attempt.twilio_sid
    assert "message_text" not in sent_events[0].payload
    assert sent_events[0].payload["message_fingerprint"] == hashlib.sha256(
        sms.send_calls[0][2].encode("utf-8")
    ).hexdigest()


def test_run_sends_follow_up_for_due_case_via_full_sweep(uow_factory) -> None:
    _make_stalled_case(uow_factory, provision_sms_number="+15005550006")
    sms = FakeSmsService()
    runner = PersistentFollowUpRunner(uow_factory, sms)

    result = runner.run(NOW)

    assert result.follow_ups_sent == 1
    assert result.follow_ups_skipped_stale == 0
    assert len(sms.send_calls) == 1


@pytest.mark.parametrize("new_state", (ProcessState.QUALIFIED, ProcessState.NEEDS_HUMAN))
def test_policy_change_after_delivery_claim_cancels_before_sms_send(
    uow_factory, monkeypatch: pytest.MonkeyPatch, new_state: ProcessState
) -> None:
    """Models a customer reply or human escalation committing after the
    durable claim but before the runner gets its dispatch lock."""
    _make_stalled_case(uow_factory)
    sms = FakeSmsService()
    runner = PersistentFollowUpRunner(uow_factory, sms)
    original = runner._authorize_and_dispatch

    def update_then_authorize(*args, **kwargs):
        _change_case_state(uow_factory, new_state)
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "_authorize_and_dispatch", update_then_authorize)

    outcome = runner._send_one(_BUSINESS_ID, _CASE_ID, NOW)

    assert outcome == "no_longer_due"
    assert sms.send_calls == []
    with uow_factory() as uow:
        case = uow.cases.get(_BUSINESS_ID, _CASE_ID)
        assert case is not None
        assert "follow_up_attempts_sent" not in case.metadata
    assert [event for event in _events(uow_factory, _BUSINESS_ID, _CASE_ID) if event.event_type == EventType.FOLLOW_UP_SENT] == []


def test_policy_change_after_provider_outcome_does_not_fabricate_follow_up_event(
    uow_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_stalled_case(uow_factory)
    sms = FakeSmsService()
    runner = PersistentFollowUpRunner(uow_factory, sms)
    original = runner._record_outcome_if_still_due

    def update_then_record(*args, **kwargs):
        _change_case_state(uow_factory, ProcessState.NEEDS_HUMAN)
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "_record_outcome_if_still_due", update_then_record)

    outcome = runner._send_one(_BUSINESS_ID, _CASE_ID, NOW)

    assert outcome == "no_longer_due"
    assert len(sms.send_calls) == 1
    with uow_factory() as uow:
        case = uow.cases.get(_BUSINESS_ID, _CASE_ID)
        assert case is not None
        assert "follow_up_attempts_sent" not in case.metadata
    assert [event for event in _events(uow_factory, _BUSINESS_ID, _CASE_ID) if event.event_type == EventType.FOLLOW_UP_SENT] == []


def test_sweep_skips_business_with_no_provisioned_number(uow_factory) -> None:
    _make_stalled_case(uow_factory)  # no provision_sms_number
    sms = FakeSmsService(number=None)
    runner = PersistentFollowUpRunner(uow_factory, sms)

    result = runner.run(NOW)

    assert result.follow_ups_sent == 0
    assert sms.send_calls == []


# --- DB conflict / crash recovery ------------------------------------------------------


def test_retry_after_case_save_conflict_does_not_resend_sms(uow_factory, monkeypatch) -> None:
    """Reproduces the original bug's crash window directly: Twilio already
    succeeded and the delivery attempt was durably marked SENT, but saving
    that back onto the case failed (StaleCaseError). A retried sweep for
    the same case/attempt must finish updating the case WITHOUT calling
    Twilio again."""
    _make_stalled_case(uow_factory)
    sms = FakeSmsService()
    runner = PersistentFollowUpRunner(uow_factory, sms)

    calls = {"n": 0}
    original_save = SQLAlchemyProcessCaseRepository.save

    def flaky_save(self, case, expected_version):
        calls["n"] += 1
        if calls["n"] == 1:
            raise StaleCaseError("simulated concurrent write")
        return original_save(self, case, expected_version)

    monkeypatch.setattr(SQLAlchemyProcessCaseRepository, "save", flaky_save)

    first_outcome = runner._send_one(_BUSINESS_ID, _CASE_ID, NOW)
    assert first_outcome == "stale"
    assert len(sms.send_calls) == 1  # Twilio really was called

    second_outcome = runner._send_one(_BUSINESS_ID, _CASE_ID, NOW)
    assert second_outcome == "sent"
    assert len(sms.send_calls) == 1  # NOT called again on retry

    with uow_factory() as uow:
        case = uow.cases.get(_BUSINESS_ID, _CASE_ID)
    assert case.metadata["follow_up_attempts_sent"] == 1
    sent_events = [e for e in _events(uow_factory, _BUSINESS_ID, _CASE_ID) if e.event_type == EventType.FOLLOW_UP_SENT]
    assert len(sent_events) == 1


def test_claim_attempt_is_idempotent_across_repeated_calls(uow_factory) -> None:
    """A second claim of the same attempt while the first is still fresh
    (within the abandoned-attempt grace period) must not create a second
    row, must not overwrite the first claim's message, and must NOT hand
    the second caller ownership of sending."""
    _make_stalled_case(uow_factory)
    with uow_factory() as uow:
        first, first_owns = uow.follow_up_deliveries.claim_attempt(
            _BUSINESS_ID, _CASE_ID, 1, message_text="original message", now=NOW
        )
        uow.commit()
    with uow_factory() as uow:
        second, second_owns = uow.follow_up_deliveries.claim_attempt(
            _BUSINESS_ID, _CASE_ID, 1, message_text="a different message", now=NOW
        )
        uow.commit()

    assert first.status == DeliveryStatus.PENDING
    assert first_owns is True
    assert second.message_text == "original message"  # not overwritten by the re-claim
    assert second.status == DeliveryStatus.PENDING
    assert second_owns is False


def test_claim_attempt_allows_takeover_of_an_abandoned_pending_row(uow_factory) -> None:
    """A PENDING row well past the grace period means the original claimer
    crashed before ever recording an outcome -- a later claimer is allowed
    to take over and actually send."""
    _make_stalled_case(uow_factory)
    with uow_factory() as uow:
        _first, first_owns = uow.follow_up_deliveries.claim_attempt(
            _BUSINESS_ID, _CASE_ID, 1, message_text="original message", now=NOW
        )
        uow.commit()
    assert first_owns is True

    much_later = NOW + timedelta(minutes=10)
    with uow_factory() as uow:
        second, second_owns = uow.follow_up_deliveries.claim_attempt(
            _BUSINESS_ID, _CASE_ID, 1, message_text="a different message", now=much_later
        )
        uow.commit()

    assert second_owns is True
    assert second.status == DeliveryStatus.PENDING


# --- Failed delivery --------------------------------------------------------------------


def test_failed_delivery_still_advances_case_and_records_failure(uow_factory) -> None:
    _make_stalled_case(uow_factory)
    sms = FakeSmsService(fail=True)
    runner = PersistentFollowUpRunner(uow_factory, sms)

    outcome = runner._send_one(_BUSINESS_ID, _CASE_ID, NOW)

    assert outcome == "sent"  # attempt consumed even though delivery failed
    assert len(sms.send_calls) == 1
    with uow_factory() as uow:
        case = uow.cases.get(_BUSINESS_ID, _CASE_ID)
        attempt, _owns = uow.follow_up_deliveries.claim_attempt(
            _BUSINESS_ID, _CASE_ID, 1, message_text="unused", now=NOW
        )
    assert case.metadata["follow_up_attempts_sent"] == 1
    assert attempt.status == DeliveryStatus.FAILED
    assert attempt.twilio_sid is None

    sent_events = [e for e in _events(uow_factory, _BUSINESS_ID, _CASE_ID) if e.event_type == EventType.FOLLOW_UP_SENT]
    assert sent_events[-1].payload["delivered"] is False
    assert sent_events[-1].payload["twilio_sid"] is None


def test_does_not_resend_when_attempt_already_recorded_as_failed(uow_factory) -> None:
    """Simulates resuming after a crash between step 2 (Twilio call +
    recording FAILED) and step 3 (updating the case) -- the runner must
    finish the case update without calling Twilio again."""
    _make_stalled_case(uow_factory)
    sms = FakeSmsService()
    runner = PersistentFollowUpRunner(uow_factory, sms)
    with uow_factory() as uow:
        uow.follow_up_deliveries.claim_attempt(_BUSINESS_ID, _CASE_ID, 1, message_text="hi", now=NOW)
        uow.follow_up_deliveries.mark_result(_BUSINESS_ID, _CASE_ID, 1, sent=False, twilio_sid=None, now=NOW)
        uow.commit()

    outcome = runner._send_one(_BUSINESS_ID, _CASE_ID, NOW)

    assert outcome == "sent"
    assert sms.send_calls == []  # never actually sent -- reused the recorded failure


# --- Not due / gone --------------------------------------------------------------------


def test_send_one_returns_gone_for_unknown_case(uow_factory) -> None:
    _make_stalled_case(uow_factory)
    sms = FakeSmsService()
    runner = PersistentFollowUpRunner(uow_factory, sms)

    outcome = runner._send_one(_BUSINESS_ID, "no-such-case", NOW)

    assert outcome == "gone"
    assert sms.send_calls == []


def test_send_one_returns_no_longer_due_before_delay_elapses(uow_factory) -> None:
    _make_stalled_case(uow_factory, last_activity=utc_now() - timedelta(hours=1))
    sms = FakeSmsService()
    runner = PersistentFollowUpRunner(uow_factory, sms)

    outcome = runner._send_one(_BUSINESS_ID, _CASE_ID, utc_now())

    assert outcome == "no_longer_due"
    assert sms.send_calls == []
