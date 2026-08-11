import pytest

from src.domain.events import EventType
from datetime import datetime, timedelta, timezone

from src.domain.models import Action, Decision, DecisionType, Lead, ProcessCase, ProcessEvent
from src.domain.state_machine import InvalidTransition
from src.domain.states import ProcessState
from src.engine.decision_router import DecisionRequest, DecisionRouter
from src.engine.process_engine import ProcessEngine


def make_case() -> ProcessCase:
    return ProcessCase("case-1", "business-1", Lead("lead-1", "Ada", email="ada@example.com"))


def advance(engine: ProcessEngine, case: ProcessCase, target: ProcessState) -> None:
    engine.receive(case, ProcessEvent("test_trigger"), DecisionRequest(DecisionType.RULE, target))


def test_engine_records_trigger_decision_and_state_change() -> None:
    case = make_case()
    trigger = ProcessEvent("lead_contacted", event_id="evt-1", source="crm")

    decision = ProcessEngine().receive(case, trigger, DecisionRequest(DecisionType.RULE, ProcessState.CONTACTED))

    assert decision.approved
    assert case.current_state is ProcessState.CONTACTED
    assert [event.event_type for event in case.event_history] == [
        "lead_contacted",
        EventType.DECISION_RECORDED,
        EventType.STATE_CHANGED,
    ]
    assert case.event_history[-1].payload == {"from": "NEW_LEAD", "to": "CONTACTED"}


def test_invalid_transition_is_audited_and_does_not_change_state() -> None:
    case = make_case()
    with pytest.raises(InvalidTransition):
        ProcessEngine().receive(case, ProcessEvent("payment_received"), DecisionRequest(DecisionType.RULE, ProcessState.PAID))

    assert case.current_state is ProcessState.NEW_LEAD
    assert case.event_history[-2].event_type is EventType.DECISION_RECORDED
    assert case.event_history[-1].event_type is EventType.TRANSITION_REJECTED


def test_low_confidence_ai_decision_escalates_to_human() -> None:
    case = make_case()
    decision = ProcessEngine().receive(
        case,
        ProcessEvent("ambiguous_message"),
        DecisionRequest(DecisionType.AI, ProcessState.CONTACTED, confidence=0.4),
    )

    assert decision.requires_human
    assert decision.approved
    assert decision.decision_type is DecisionType.HUMAN
    assert case.current_state is ProcessState.NEEDS_HUMAN
    assert case.pending_transition is ProcessState.CONTACTED


def test_high_risk_ai_decision_escalates_even_with_high_confidence() -> None:
    case = make_case()
    ProcessEngine().receive(
        case,
        ProcessEvent("risky_request"),
        DecisionRequest(DecisionType.AI, ProcessState.CONTACTED, confidence=0.99, high_risk=True),
    )
    assert case.current_state is ProcessState.NEEDS_HUMAN


def test_protected_action_escalates_even_when_rule_does_not_mark_it_high_risk() -> None:
    case = make_case()
    decision = ProcessEngine().receive(
        case,
        ProcessEvent("payment_attempt"),
        DecisionRequest(
            DecisionType.RULE,
            ProcessState.CONTACTED,
            action=Action("capture_payment"),
        ),
    )
    assert decision.requires_human
    assert case.current_state is ProcessState.NEEDS_HUMAN


def test_only_identified_human_can_approve_exact_pending_target() -> None:
    case = make_case()
    engine = ProcessEngine()
    engine.receive(
        case,
        ProcessEvent("ambiguous"),
        DecisionRequest(DecisionType.AI, ProcessState.CONTACTED, confidence=0.1),
    )

    with pytest.raises(InvalidTransition, match="identified human"):
        engine.receive(
            case,
            ProcessEvent("fake_resolution"),
            DecisionRequest(DecisionType.RULE, ProcessState.CONTACTED),
        )
    with pytest.raises(InvalidTransition, match="pending transition"):
        engine.receive(
            case,
            ProcessEvent("wrong_resolution"),
            DecisionRequest(DecisionType.HUMAN, ProcessState.PAID, approved_by="operator-1"),
        )

    engine.receive(
        case,
        ProcessEvent("approved_resolution"),
        DecisionRequest(DecisionType.HUMAN, ProcessState.CONTACTED, approved_by="operator-1"),
    )
    assert case.current_state is ProcessState.CONTACTED
    assert case.pending_transition is None
    assert case.event_history[-2].payload["metadata"]["approved_by"] == "operator-1"


class MismatchedAIProvider:
    def decide(self, case: ProcessCase, event: ProcessEvent, request: DecisionRequest) -> Decision:
        return Decision(DecisionType.RULE, True, "spoofed", ProcessState.PAID, 1.0)


def test_untrusted_ai_provider_cannot_change_type_or_target() -> None:
    case = make_case()
    engine = ProcessEngine(decision_router=DecisionRouter(ai_provider=MismatchedAIProvider()))
    decision = engine.receive(
        case,
        ProcessEvent("ai_request"),
        DecisionRequest(DecisionType.AI, ProcessState.CONTACTED, confidence=1.0),
    )
    assert decision.requires_human
    assert case.current_state is ProcessState.NEEDS_HUMAN
    assert case.pending_transition is ProcessState.CONTACTED


def test_duplicate_trigger_is_idempotent() -> None:
    case = make_case()
    engine = ProcessEngine()
    event = ProcessEvent("lead_contacted", event_id="same-event")
    request = DecisionRequest(DecisionType.RULE, ProcessState.CONTACTED)

    engine.receive(case, event, request)
    decision = engine.receive(case, event, request)

    assert not decision.approved
    assert case.current_state is ProcessState.CONTACTED
    assert case.event_history[-1].event_type is EventType.DUPLICATE_IGNORED
    assert sum(event.event_type is EventType.STATE_CHANGED for event in case.event_history) == 1
    assert case.event_history[-1].causation_id == "same-event"


def test_audit_payload_and_history_cannot_be_mutated_externally() -> None:
    event = ProcessEvent("lead", payload={"nested": {"items": [1, 2]}})
    case = make_case()
    ProcessEngine().receive(case, event, DecisionRequest(DecisionType.RULE, ProcessState.CONTACTED))

    with pytest.raises(TypeError):
        event.payload["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        event.payload["nested"]["new"] = "value"  # type: ignore[index]
    assert isinstance(case.event_history, tuple)
    with pytest.raises(AttributeError):
        case.current_state = ProcessState.PAID  # type: ignore[misc]


def test_old_event_timestamp_does_not_move_case_updated_at_backwards() -> None:
    case = make_case()
    before = case.updated_at
    old_event = ProcessEvent("delayed", occurred_at=datetime.now(timezone.utc) - timedelta(days=1))
    ProcessEngine().receive(case, old_event, DecisionRequest(DecisionType.RULE, ProcessState.CONTACTED))
    assert case.updated_at >= before


def test_invalid_ids_naive_timestamps_and_confidence_are_rejected() -> None:
    with pytest.raises(ValueError, match="case_id"):
        ProcessCase(" ", "business-1", Lead("lead-1", "Ada"))
    with pytest.raises(ValueError, match="timezone-aware"):
        ProcessEvent("event", occurred_at=datetime.now())
    with pytest.raises(ValueError, match="confidence"):
        DecisionRequest(DecisionType.AI, ProcessState.CONTACTED, confidence=1.1)


def test_basic_lead_to_cash_progression_through_quote_branch() -> None:
    case = make_case()
    engine = ProcessEngine()
    path = [
        ProcessState.CONTACTED,
        ProcessState.QUALIFYING,
        ProcessState.QUALIFIED,
        ProcessState.QUOTED,
        ProcessState.FOLLOW_UP,
        ProcessState.WON,
        ProcessState.PAID,
        ProcessState.COMPLETED,
        ProcessState.REVIEW_REQUESTED,
        ProcessState.REACTIVATION,
    ]
    for state in path:
        advance(engine, case, state)

    assert case.current_state is ProcessState.REACTIVATION
    assert len(case.event_history) == len(path) * 3
