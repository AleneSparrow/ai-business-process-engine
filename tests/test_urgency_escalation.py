"""Emergency vs. high-urgency escalation policy.

Decision 2026-08-24 (claude/unit-economics-and-urgency-default.md, variant
C): a live 40-vertical run caught "Our ceiling is leaking after the storm"
escalating straight to NEEDS_HUMAN before a single qualifying question was
asked -- for roofing, plumbing, HVAC, PI law, "high" urgency is the normal
case, not the exception, so automation was switching itself off exactly
where speed mattered most.

emergency (life/safety/active-damage threat) still escalates immediately,
unchanged. A merely "high" urgency lead (leaking ceiling, "need it today")
now completes the ordinary qualification cycle -- name, phone, service --
and only then hands off to a person, with a full card instead of a bare
"someone said something urgent". The branching is purely on Urgency, not
industry: src/ has no vertical-specific logic and this adds none.
"""

from datetime import datetime, timezone

from src.domain.business_dna_builder import OnboardingInput, OnboardingService, build_business_dna
from src.domain.events import EventType
from src.domain.qualification import IncomingMessage, IntentResult, Urgency
from src.domain.states import ProcessState
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.engine.lead_intake import LeadIntakeService
from src.engine.question_generator import DeterministicQuestionGenerator

NOW = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)
BUSINESS_ID = "urgency-test-roofing"


def _dna(**overrides: object) -> dict:
    defaults: dict[str, object] = dict(
        business_id=BUSINESS_ID,
        business_name="Test Roofing Co",
        industry="Roofing",
        tone="Friendly & direct",
        services=(OnboardingService("Roof repair"),),
        service_zip_codes=(),
        enforce_service_area=False,
    )
    defaults.update(overrides)
    return build_business_dna(OnboardingInput(**defaults))  # type: ignore[arg-type]


def _message(
    external_id: str,
    *,
    name: str | None = None,
    phone: str | None = None,
    case_id: str | None = None,
) -> IncomingMessage:
    return IncomingMessage(
        business_id=BUSINESS_ID,
        # build_business_dna only enables "webchat" by default (see
        # business_dna_builder.py) -- this DNA is built via that helper.
        channel="webchat",
        external_message_id=external_id,
        customer_name=name,
        phone=phone,
        email=None,
        raw_text="the ceiling is leaking after the storm",
        timestamp=NOW,
        case_id=case_id,
    )


def _intake(results: dict[str, IntentResult], dna: dict | None = None) -> LeadIntakeService:
    return LeadIntakeService(
        dna or _dna(),
        DeterministicIntentExtractor(results),
        DeterministicQuestionGenerator(),
    )


def test_emergency_escalates_immediately_before_qualification() -> None:
    """Requirement 1: nothing changes for a genuine emergency -- it still
    preempts qualification entirely, no name/phone collected first."""
    intake = _intake({
        "msg": IntentResult(service_requested="roof-repair", urgency=Urgency.EMERGENCY, confidence=0.95),
    })

    result = intake.receive(_message("msg"))

    assert result.current_state is ProcessState.NEEDS_HUMAN
    assert result.qualification.requires_human
    assert result.qualification.missing_fields == ()


def test_high_urgency_completes_qualification_before_escalating() -> None:
    """Requirement 2: a high-urgency lead is NOT stopped mid-cycle -- it
    keeps collecting name/phone like any other lead, and only escalates
    (with the service and contact details already known) once qualified."""
    intake = _intake({
        "msg-a": IntentResult(service_requested="roof-repair", urgency=Urgency.HIGH, confidence=0.95),
        "msg-b": IntentResult(urgency=Urgency.HIGH, confidence=0.95),
    })

    first = intake.receive(_message("msg-a"))
    second = intake.receive(_message(
        "msg-b", name="Sarah Chen", phone="+1 312 555 0100", case_id=first.case_id,
    ))

    assert first.current_state is ProcessState.QUALIFYING
    assert not first.qualification.requires_human
    assert first.qualification.missing_fields == ("name", "phone")
    assert first.response is not None and not first.response.requires_human

    assert second.current_state is ProcessState.NEEDS_HUMAN
    assert second.qualification.requires_human
    assert second.qualification.service_id == "roof-repair"
    assert "urgency" in second.qualification.reasons[0].casefold()
    assert second.response is not None and second.response.requires_human

    qualification_event = next(
        event
        for event in intake.get_case(second.case_id).event_history
        if event.event_type is EventType.QUALIFICATION_EVALUATED
        and event.payload["recommended_next_state"] == "NEEDS_HUMAN"
    )
    assert qualification_event.payload["escalation_reason"] == "urgent_request"


def test_normal_urgency_lead_is_not_affected() -> None:
    """An ordinary lead reaches QUALIFIED exactly as before -- this feature
    only changes behavior for HIGH (and leaves EMERGENCY untouched)."""
    intake = _intake({
        "msg-a": IntentResult(service_requested="roof-repair", urgency=Urgency.NORMAL, confidence=0.95),
        "msg-b": IntentResult(urgency=Urgency.NORMAL, confidence=0.95),
    })

    first = intake.receive(_message("msg-a"))
    second = intake.receive(_message(
        "msg-b", name="Sarah Chen", phone="+1 312 555 0100", case_id=first.case_id,
    ))

    assert second.current_state is ProcessState.QUALIFIED
    assert second.qualification.qualified
    assert not second.qualification.requires_human


def test_business_with_explicit_high_urgency_escalation_keeps_immediate_handoff() -> None:
    """Requirement 4: escalate_on_high_urgency=True is still honored exactly
    as before -- an owner who explicitly opts back into the old behavior
    gets immediate escalation, before qualification, same as pre-2026-08-24."""
    dna = _dna(escalate_on_high_urgency=True)
    assert "high" in dna["human_escalation"]["triggers"]
    intake = _intake({
        "msg": IntentResult(service_requested="roof-repair", urgency=Urgency.HIGH, confidence=0.95),
    }, dna=dna)

    result = intake.receive(_message("msg"))

    assert result.current_state is ProcessState.NEEDS_HUMAN
    assert result.qualification.requires_human
    assert result.qualification.missing_fields == ()


def test_new_business_defaults_to_not_stopping_the_cycle_on_high_urgency() -> None:
    """The default itself changed: a freshly onboarded business (no explicit
    escalate_on_high_urgency) does not have "high" as an immediate trigger."""
    dna = _dna()

    assert "high" not in dna["human_escalation"]["triggers"]
    assert "emergency" in dna["human_escalation"]["triggers"]
