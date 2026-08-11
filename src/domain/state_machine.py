"""Explicit transition policy for the reusable Lead-to-Cash lifecycle."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .states import ProcessState


class InvalidTransition(ValueError):
    """Raised when a requested state change violates the workflow."""


TRANSITIONS: dict[ProcessState, frozenset[ProcessState]] = {
    ProcessState.NEW_LEAD: frozenset({ProcessState.CONTACTED, ProcessState.NEEDS_HUMAN, ProcessState.LOST}),
    ProcessState.CONTACTED: frozenset({ProcessState.QUALIFYING, ProcessState.NEEDS_HUMAN, ProcessState.LOST}),
    ProcessState.QUALIFYING: frozenset({ProcessState.QUALIFIED, ProcessState.NEEDS_HUMAN, ProcessState.LOST}),
    ProcessState.QUALIFIED: frozenset({ProcessState.BOOKED, ProcessState.QUOTED, ProcessState.NEEDS_HUMAN, ProcessState.LOST}),
    ProcessState.BOOKED: frozenset({ProcessState.FOLLOW_UP, ProcessState.CANCELLED, ProcessState.NEEDS_HUMAN}),
    ProcessState.QUOTED: frozenset({ProcessState.FOLLOW_UP, ProcessState.LOST, ProcessState.NEEDS_HUMAN}),
    ProcessState.FOLLOW_UP: frozenset({ProcessState.WON, ProcessState.LOST, ProcessState.NEEDS_HUMAN}),
    ProcessState.WON: frozenset({ProcessState.PAID, ProcessState.CANCELLED, ProcessState.NEEDS_HUMAN}),
    ProcessState.PAID: frozenset({ProcessState.COMPLETED, ProcessState.NEEDS_HUMAN}),
    ProcessState.COMPLETED: frozenset({ProcessState.REVIEW_REQUESTED, ProcessState.NEEDS_HUMAN}),
    ProcessState.REVIEW_REQUESTED: frozenset({ProcessState.REACTIVATION, ProcessState.NEEDS_HUMAN}),
    ProcessState.REACTIVATION: frozenset({ProcessState.CONTACTED, ProcessState.LOST, ProcessState.NEEDS_HUMAN}),
    ProcessState.NEEDS_HUMAN: frozenset(),
    ProcessState.LOST: frozenset({ProcessState.REACTIVATION}),
    ProcessState.CANCELLED: frozenset({ProcessState.REACTIVATION}),
}


@dataclass(frozen=True, slots=True)
class StateMachine:
    transitions: Mapping[ProcessState, frozenset[ProcessState]]

    def __init__(self, transitions: Mapping[ProcessState, frozenset[ProcessState]] | None = None) -> None:
        source = TRANSITIONS if transitions is None else transitions
        if set(source) != set(ProcessState):
            raise ValueError("transitions must define every process state exactly once")
        normalized: dict[ProcessState, frozenset[ProcessState]] = {}
        for state, targets in source.items():
            if not isinstance(state, ProcessState):
                raise TypeError("transition keys must be ProcessState values")
            frozen_targets = frozenset(targets)
            if any(not isinstance(target, ProcessState) for target in frozen_targets):
                raise TypeError("transition targets must be ProcessState values")
            if state in frozen_targets:
                raise ValueError(f"self-transition is not allowed for {state.value}")
            normalized[state] = frozen_targets
        object.__setattr__(self, "transitions", MappingProxyType(normalized))

    def can_transition(self, current: ProcessState, target: ProcessState) -> bool:
        return target in self.transitions.get(current, frozenset()) and target != current

    def validate(self, current: ProcessState, target: ProcessState) -> None:
        if not self.can_transition(current, target):
            raise InvalidTransition(f"Cannot transition from {current.value} to {target.value}")
