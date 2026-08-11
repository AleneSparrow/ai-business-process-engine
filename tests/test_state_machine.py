import pytest

from src.domain.state_machine import InvalidTransition, StateMachine
from src.domain.states import ProcessState


def test_valid_state_transition() -> None:
    machine = StateMachine()
    machine.validate(ProcessState.NEW_LEAD, ProcessState.CONTACTED)


def test_invalid_state_transition_is_rejected() -> None:
    machine = StateMachine()
    with pytest.raises(InvalidTransition, match="NEW_LEAD to PAID"):
        machine.validate(ProcessState.NEW_LEAD, ProcessState.PAID)


def test_quote_and_booking_are_alternative_qualified_paths() -> None:
    machine = StateMachine()
    assert machine.can_transition(ProcessState.QUALIFIED, ProcessState.BOOKED)
    assert machine.can_transition(ProcessState.QUALIFIED, ProcessState.QUOTED)


def test_booking_and_quote_must_enter_follow_up_before_won() -> None:
    machine = StateMachine()
    assert machine.can_transition(ProcessState.BOOKED, ProcessState.FOLLOW_UP)
    assert machine.can_transition(ProcessState.QUOTED, ProcessState.FOLLOW_UP)
    assert not machine.can_transition(ProcessState.BOOKED, ProcessState.WON)
    assert not machine.can_transition(ProcessState.QUOTED, ProcessState.WON)


def test_paid_case_cannot_be_directly_cancelled() -> None:
    assert not StateMachine().can_transition(ProcessState.PAID, ProcessState.CANCELLED)


def test_human_escalation_has_no_unrestricted_static_exit() -> None:
    machine = StateMachine()
    assert machine.transitions[ProcessState.NEEDS_HUMAN] == frozenset()


def test_transition_policy_is_immutable_and_must_cover_every_state() -> None:
    machine = StateMachine()
    with pytest.raises(TypeError):
        machine.transitions[ProcessState.NEW_LEAD] = frozenset()  # type: ignore[index]
    with pytest.raises(ValueError, match="every process state"):
        StateMachine({ProcessState.NEW_LEAD: frozenset({ProcessState.CONTACTED})})
