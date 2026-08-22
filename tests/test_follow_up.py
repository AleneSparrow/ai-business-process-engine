"""Proactive stalled-lead follow-up (universal-sales-cycle-model.md section 8).

Covers only the pure, dependency-free decision/composition logic in
src/engine/follow_up.py -- the DB scan and actual SMS send
(src/persistence/follow_up_service.py) need SQLAlchemy, unavailable in this
sandbox; that layer is hand-reviewed against this same test coverage instead
(see PersistentFollowUpRunner's docstring).
"""

from datetime import datetime, timedelta, timezone

from src.domain.events import EventType
from src.domain.models import Lead, ProcessCase, ProcessEvent
from src.domain.qualification import MissingInformationResult
from src.domain.states import ProcessState
from src.engine.follow_up import (
    DeterministicFollowUpMessageGenerator,
    decide_follow_up,
    missing_information_from_case,
    record_follow_up_sent,
)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

BUSINESS_DNA = {
    "business": {"name": "Acme Home Services"},
    "sales": {"follow_up": {"delays_hours": [24, 72, 168], "maximum_attempts": 3}},
    "customer_information": {
        "field_questions": {"phone": "What is the best number to reach you?"},
    },
}


def make_case(
    state: ProcessState,
    *,
    consent: bool = True,
    phone: str | None = "+15551234567",
    last_activity: datetime | None = None,
    attempts_sent: int = 0,
    missing_fields: tuple[str, ...] = ("phone",),
) -> ProcessCase:
    lead = Lead("lead-1", "Ada", None, phone, sms_consent=consent)
    case = ProcessCase("case-1", "biz-1", lead, current_state=state, created_at=NOW - timedelta(days=10))
    if last_activity is not None:
        case.record(ProcessEvent(EventType.LEAD_INTAKE_RECEIVED, occurred_at=last_activity, source="sms"))
    case.record(ProcessEvent(
        EventType.QUALIFICATION_EVALUATED,
        occurred_at=last_activity or NOW,
        source="qualification_service",
        payload={"missing_fields": list(missing_fields), "unanswered_questions": []},
    ))
    if attempts_sent:
        case.metadata["follow_up_attempts_sent"] = attempts_sent
    return case


def test_not_due_before_first_delay_elapses() -> None:
    case = make_case(ProcessState.QUALIFYING, last_activity=NOW - timedelta(hours=5))
    decision = decide_follow_up(case, BUSINESS_DNA, NOW)
    assert decision.due is False
    assert decision.reason == "delay_not_elapsed"


def test_due_once_first_delay_elapses() -> None:
    case = make_case(ProcessState.QUALIFYING, last_activity=NOW - timedelta(hours=25))
    decision = decide_follow_up(case, BUSINESS_DNA, NOW)
    assert decision.due is True
    assert decision.attempt_number == 1


def test_not_due_without_sms_consent() -> None:
    case = make_case(ProcessState.QUALIFYING, consent=False, last_activity=NOW - timedelta(hours=25))
    decision = decide_follow_up(case, BUSINESS_DNA, NOW)
    assert decision.due is False
    assert decision.reason == "no_sms_consent"


def test_not_due_without_phone() -> None:
    case = make_case(ProcessState.QUALIFYING, phone=None, last_activity=NOW - timedelta(hours=25))
    decision = decide_follow_up(case, BUSINESS_DNA, NOW)
    assert decision.due is False
    assert decision.reason == "no_phone"


def test_not_due_once_qualified() -> None:
    """A case that already progressed past qualification is not "stalled"
    in section 8's sense -- QUALIFIED/BOOKED/QUOTED/etc. are out of scope
    for this reactive-recovery layer (and QUALIFIED-but-not-booked nudging,
    if wanted later, is a deliberately separate decision -- see the delivery
    note to Alena)."""
    case = make_case(ProcessState.QUALIFIED, last_activity=NOW - timedelta(hours=200))
    decision = decide_follow_up(case, BUSINESS_DNA, NOW)
    assert decision.due is False
    assert decision.reason == "case_not_in_stalled_state"


def test_not_due_when_needs_human() -> None:
    """A human is already expected to be handling this case -- an automated
    nudge here could cross wires with what they're about to send."""
    case = make_case(ProcessState.NEEDS_HUMAN, last_activity=NOW - timedelta(hours=200))
    decision = decide_follow_up(case, BUSINESS_DNA, NOW)
    assert decision.due is False
    assert decision.reason == "case_not_in_stalled_state"


def test_not_due_once_max_attempts_reached() -> None:
    case = make_case(ProcessState.QUALIFYING, last_activity=NOW - timedelta(hours=200), attempts_sent=3)
    decision = decide_follow_up(case, BUSINESS_DNA, NOW)
    assert decision.due is False
    assert decision.reason == "max_attempts_reached"


def test_second_attempt_measured_from_last_activity() -> None:
    """delays_hours[1] (72h) governs the SECOND attempt -- gap measured from
    the case's last activity (its last inbound message, or if a follow-up
    was already sent, that), not from the very first stall."""
    case = make_case(ProcessState.QUALIFYING, last_activity=NOW - timedelta(hours=100), attempts_sent=1)
    decision = decide_follow_up(case, BUSINESS_DNA, NOW)
    assert decision.due is True
    assert decision.attempt_number == 2


def test_not_due_without_follow_up_configured() -> None:
    case = make_case(ProcessState.QUALIFYING, last_activity=NOW - timedelta(hours=200))
    decision = decide_follow_up(case, {"business": {}}, NOW)
    assert decision.due is False
    assert decision.reason == "follow_up_not_configured"


def test_not_due_with_malformed_follow_up_config() -> None:
    """A sweep across many businesses must not crash on one business's
    malformed config -- treated the same as "not configured", not an
    exception."""
    dna = {"business": {}, "sales": {"follow_up": {"delays_hours": [], "maximum_attempts": 3}}}
    case = make_case(ProcessState.QUALIFYING, last_activity=NOW - timedelta(hours=200))
    decision = decide_follow_up(case, dna, NOW)
    assert decision.due is False
    assert decision.reason == "follow_up_not_configured"


def test_record_follow_up_sent_increments_monotonically() -> None:
    case = make_case(ProcessState.QUALIFYING, last_activity=NOW - timedelta(hours=25))
    assert case.metadata.get("follow_up_attempts_sent", 0) == 0
    record_follow_up_sent(case)
    assert case.metadata["follow_up_attempts_sent"] == 1
    record_follow_up_sent(case)
    assert case.metadata["follow_up_attempts_sent"] == 2


def test_missing_information_from_case_reads_latest_qualification_event() -> None:
    case = make_case(
        ProcessState.QUALIFYING,
        last_activity=NOW - timedelta(hours=25),
        missing_fields=("phone", "customer_location"),
    )
    missing = missing_information_from_case(case)
    assert missing.missing_fields == ("phone", "customer_location")


def test_missing_information_from_case_defaults_to_empty_without_any_evaluation() -> None:
    case = ProcessCase("case-2", "biz-1", Lead("lead-2", None, None, "+15551234567", sms_consent=True))
    missing = missing_information_from_case(case)
    assert missing == MissingInformationResult()


def test_deterministic_generator_restates_outstanding_question() -> None:
    generator = DeterministicFollowUpMessageGenerator()
    missing = MissingInformationResult(("phone",), ())
    response = generator.generate(missing, BUSINESS_DNA, "sms", "case-1", attempt_number=1)
    assert "Acme Home Services" in response.message_text
    assert "best number to reach you" in response.message_text
    assert response.reason == "follow_up"
    assert response.channel == "sms"
    assert response.related_case_id == "case-1"


def test_deterministic_generator_falls_back_to_check_in_when_nothing_missing() -> None:
    generator = DeterministicFollowUpMessageGenerator()
    response = generator.generate(MissingInformationResult(), BUSINESS_DNA, "sms", "case-1", attempt_number=2)
    assert "still interested" in response.message_text


def test_deterministic_generator_never_invents_a_business_name() -> None:
    """No `business.name` configured -> generic greeting, never a fabricated
    or omitted-but-implied business identity."""
    generator = DeterministicFollowUpMessageGenerator()
    dna_without_name = {"business": {}}
    response = generator.generate(MissingInformationResult(), dna_without_name, "sms", "case-1", attempt_number=1)
    assert response.message_text.startswith("Hi --")
