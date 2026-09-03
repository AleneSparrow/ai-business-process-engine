"""Inbound SMS threads appear on Conversations; staff replies go back out."""

from datetime import datetime, timezone

from src.domain.auth import StaffUser
from src.domain.conversations import ConversationStatus, MessageDirection
from src.domain.models import Lead, ProcessCase, utc_now
from src.domain.qualification import (
    CustomerResponse,
    LeadIntakeResult,
    QualificationReasonCode,
    QualificationResult,
)
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.sms_thread_service import SMS_CHANNEL, SmsThreadService
from src.persistence.staff_action_service import StaffActionService
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _factory(tmp_path):
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'sms-thread.db'}")
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    now = utc_now()
    with factory() as uow:
        uow.businesses.add(Business("tenant-a", "Tenant A", now, now))
        uow.leads.add("tenant-a", Lead("lead-1", "Ada", None, "+15551234567"), now)
        case = ProcessCase("case-1", "tenant-a", uow.leads.get("tenant-a", "lead-1"), ProcessState.QUALIFYING, now, now)
        uow.cases.add(case)
        uow.commit()
    return factory, engine


def _intake(*, human: bool = False) -> LeadIntakeResult:
    state = ProcessState.NEEDS_HUMAN if human else ProcessState.QUALIFYING
    qualification = QualificationResult(
        qualified=False,
        reasons=("needs a person",) if human else ("missing service",),
        reason_codes=(
            QualificationReasonCode.REQUIRES_HUMAN.value
            if human
            else QualificationReasonCode.MISSING_INFORMATION.value,
        ),
        missing_fields=() if human else ("service",),
        unanswered_questions=(),
        confidence=0.4 if human else 0.9,
        recommended_next_state=state,
        requires_human=human,
        booking_allowed=False,
    )
    return LeadIntakeResult(
        case_id="case-1",
        lead_id="lead-1",
        current_state=state,
        qualification=qualification,
        response=CustomerResponse(
            "Thanks — what service do you need?",
            "sms",
            "ask",
            "case-1",
        ),
        case_created=True,
    )


def test_sync_from_intake_creates_staff_visible_sms_thread(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    SmsThreadService(factory).sync_from_intake(
        "tenant-a",
        "+15551234567",
        body="I need a consult",
        inbound_message_id="SM1",
        intake=_intake(),
    )
    with factory() as uow:
        conversation = uow.conversations.get_by_channel_session(
            "tenant-a", SMS_CHANNEL, "+15551234567"
        )
        assert conversation is not None
        assert conversation.lead_id == "lead-1"
        assert conversation.case_id == "case-1"
        messages = uow.conversation_messages.list_for_conversation(
            "tenant-a", conversation.conversation_id
        )
        assert [m.direction for m in messages] == [MessageDirection.INBOUND, MessageDirection.OUTBOUND]
        assert messages[0].text == "I need a consult"
    engine.dispose()


def test_needs_human_pauses_the_sms_thread(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    threads = SmsThreadService(factory)
    threads.sync_from_intake(
        "tenant-a",
        "+15551234567",
        body="this is urgent",
        inbound_message_id="SM2",
        intake=_intake(human=True),
    )
    assert threads.is_paused("tenant-a", "+15551234567")
    with factory() as uow:
        conversation = uow.conversations.get_by_channel_session(
            "tenant-a", SMS_CHANNEL, "+15551234567"
        )
        assert conversation is not None
        assert conversation.status is ConversationStatus.HUMAN_TAKEOVER_REQUESTED
    engine.dispose()


def test_staff_reply_on_sms_thread_enqueues_outbound(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    threads = SmsThreadService(factory)
    threads.sync_from_intake(
        "tenant-a",
        "+15551234567",
        body="hello",
        inbound_message_id="SM3",
        intake=_intake(human=True),
    )
    with factory() as uow:
        conversation = uow.conversations.get_by_channel_session(
            "tenant-a", SMS_CHANNEL, "+15551234567"
        )
        assert conversation is not None
        conversation_id = conversation.conversation_id

    sent: list[tuple[str, str]] = []

    class _Sms:
        def enqueue_reply(self, business_id, *, to_number, body, inbound_message_id, ignore_suppression=False):
            sent.append((to_number, body))

    staff = StaffUser(
        "user-1",
        "owner@example.com",
        "owner@example.com",
        "hash",
        "tenant-a",
        NOW,
        ("tenant-a",),
    )
    StaffActionService(factory, sms_service=_Sms()).reply(
        "tenant-a", conversation_id, staff, "We can take this on Tuesday."
    )
    assert sent == [("+15551234567", "We can take this on Tuesday.")]
    engine.dispose()
