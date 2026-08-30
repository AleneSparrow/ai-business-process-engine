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


def test_validate_human_resume_accepts_exact_pending_target() -> None:
    StateMachine().validate_human_resume(ProcessState.NEEDS_HUMAN, ProcessState.CONTACTED, ProcessState.CONTACTED)


def test_validate_human_resume_rejects_when_current_state_is_not_needs_human() -> None:
    with pytest.raises(InvalidTransition, match="NEEDS_HUMAN"):
        StateMachine().validate_human_resume(ProcessState.QUALIFYING, ProcessState.CONTACTED, ProcessState.CONTACTED)


def test_validate_human_resume_rejects_without_a_pending_transition() -> None:
    with pytest.raises(InvalidTransition, match="no pending transition"):
        StateMachine().validate_human_resume(ProcessState.NEEDS_HUMAN, None, ProcessState.CONTACTED)


def test_validate_human_resume_rejects_target_that_does_not_match_pending() -> None:
    with pytest.raises(InvalidTransition, match="does not match"):
        StateMachine().validate_human_resume(ProcessState.NEEDS_HUMAN, ProcessState.CONTACTED, ProcessState.PAID)


def test_validate_human_resume_does_not_widen_the_static_transition_table() -> None:
    """validate_human_resume authorizes a resume independently of
    `transitions` -- it must never be mistaken for (or implemented by)
    adding real NEEDS_HUMAN entries to the static table."""
    machine = StateMachine()
    machine.validate_human_resume(ProcessState.NEEDS_HUMAN, ProcessState.PAID, ProcessState.PAID)
    assert machine.transitions[ProcessState.NEEDS_HUMAN] == frozenset()
    assert not machine.can_transition(ProcessState.NEEDS_HUMAN, ProcessState.PAID)


def test_transition_policy_is_immutable_and_must_cover_every_state() -> None:
    machine = StateMachine()
    with pytest.raises(TypeError):
        machine.transitions[ProcessState.NEW_LEAD] = frozenset()  # type: ignore[index]
    with pytest.raises(ValueError, match="every process state"):
        StateMachine({ProcessState.NEW_LEAD: frozenset({ProcessState.CONTACTED})})
