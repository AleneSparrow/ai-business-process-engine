"""Explicit transition policy for Demand campaign setup and prospect journeys."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .states import CampaignState, ProspectState


class InvalidDemandTransition(ValueError):
    """Raised when a requested Demand state change violates the workflow."""


CAMPAIGN_TRANSITIONS: dict[CampaignState, frozenset[CampaignState]] = {
    CampaignState.MARKET_ANALYSIS: frozenset({CampaignState.SEGMENTS_READY, CampaignState.NEEDS_HUMAN}),
    CampaignState.SEGMENTS_READY: frozenset({CampaignState.POSITIONED, CampaignState.NEEDS_HUMAN}),
    CampaignState.POSITIONED: frozenset({CampaignState.MOTION_SELECTED, CampaignState.NEEDS_HUMAN}),
    CampaignState.MOTION_SELECTED: frozenset({CampaignState.ASSETS_READY, CampaignState.NEEDS_HUMAN}),
    CampaignState.ASSETS_READY: frozenset({CampaignState.LIVE, CampaignState.NEEDS_HUMAN}),
    CampaignState.LIVE: frozenset({CampaignState.PAUSED, CampaignState.NEEDS_HUMAN}),
    CampaignState.PAUSED: frozenset({CampaignState.LIVE, CampaignState.ASSETS_READY, CampaignState.NEEDS_HUMAN}),
    CampaignState.NEEDS_HUMAN: frozenset(),
}


PROSPECT_TRANSITIONS: dict[ProspectState, frozenset[ProspectState]] = {
    # Skip-ahead is first-class: a person may inquire from the first touch.
    ProspectState.UNKNOWN: frozenset({
        ProspectState.AWARE,
        ProspectState.ENGAGED,
        ProspectState.SUBSCRIBED,
        ProspectState.INTENT,
        ProspectState.INQUIRED,
        ProspectState.SUPPRESSED,
        ProspectState.NEEDS_HUMAN,
    }),
    ProspectState.AWARE: frozenset({
        ProspectState.ENGAGED,
        ProspectState.SUBSCRIBED,
        ProspectState.INTENT,
        ProspectState.INQUIRED,
        ProspectState.SUPPRESSED,
        ProspectState.EXPIRED,
        ProspectState.NEEDS_HUMAN,
    }),
    ProspectState.ENGAGED: frozenset({
        ProspectState.SUBSCRIBED,
        ProspectState.INTENT,
        ProspectState.INQUIRED,
        ProspectState.SUPPRESSED,
        ProspectState.EXPIRED,
        ProspectState.NEEDS_HUMAN,
    }),
    ProspectState.SUBSCRIBED: frozenset({
        ProspectState.NURTURING,
        ProspectState.INTENT,
        ProspectState.INQUIRED,
        ProspectState.SUPPRESSED,
        ProspectState.NEEDS_HUMAN,
    }),
    ProspectState.NURTURING: frozenset({
        ProspectState.INTENT,
        ProspectState.INQUIRED,
        ProspectState.SUPPRESSED,
        ProspectState.EXPIRED,
        ProspectState.NEEDS_HUMAN,
    }),
    ProspectState.INTENT: frozenset({
        ProspectState.INQUIRED,
        ProspectState.NURTURING,
        ProspectState.SUPPRESSED,
        ProspectState.EXPIRED,
        ProspectState.NEEDS_HUMAN,
    }),
    ProspectState.INQUIRED: frozenset({ProspectState.HANDED_OFF, ProspectState.NEEDS_HUMAN}),
    ProspectState.HANDED_OFF: frozenset(),
    ProspectState.SUPPRESSED: frozenset({ProspectState.SUBSCRIBED}),
    ProspectState.EXPIRED: frozenset({
        ProspectState.NURTURING,
        ProspectState.SUBSCRIBED,
        ProspectState.INQUIRED,
        ProspectState.SUPPRESSED,
        ProspectState.NEEDS_HUMAN,
    }),
    ProspectState.NEEDS_HUMAN: frozenset(),
}


def _freeze_table(source: Mapping, enum_type: type) -> Mapping:
    if set(source) != set(enum_type):
        raise ValueError(f"transitions must define every {enum_type.__name__} exactly once")
    normalized = {}
    for state, targets in source.items():
        if not isinstance(state, enum_type):
            raise TypeError("transition keys must be state enum values")
        frozen_targets = frozenset(targets)
        if any(not isinstance(target, enum_type) for target in frozen_targets):
            raise TypeError("transition targets must be state enum values")
        if state in frozen_targets:
            raise ValueError(f"self-transition is not allowed for {state.value}")
        normalized[state] = frozen_targets
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class CampaignStateMachine:
    transitions: Mapping[CampaignState, frozenset[CampaignState]]

    def __init__(self, transitions: Mapping[CampaignState, frozenset[CampaignState]] | None = None) -> None:
        source = CAMPAIGN_TRANSITIONS if transitions is None else transitions
        object.__setattr__(self, "transitions", _freeze_table(source, CampaignState))

    def can_transition(self, current: CampaignState, target: CampaignState) -> bool:
        return target in self.transitions.get(current, frozenset()) and target != current

    def validate(self, current: CampaignState, target: CampaignState) -> None:
        if not self.can_transition(current, target):
            raise InvalidDemandTransition(f"Cannot transition from {current.value} to {target.value}")

    def validate_human_resume(
        self,
        current: CampaignState,
        pending_transition: CampaignState | None,
        target: CampaignState,
    ) -> None:
        if current is not CampaignState.NEEDS_HUMAN:
            raise InvalidDemandTransition("validate_human_resume only applies to NEEDS_HUMAN campaigns")
        if pending_transition is None:
            raise InvalidDemandTransition("NEEDS_HUMAN campaign has no pending transition to resume")
        if target is not pending_transition:
            raise InvalidDemandTransition(
                f"Human approval target {target.value} does not match "
                f"pending transition {pending_transition.value}"
            )


@dataclass(frozen=True, slots=True)
class ProspectStateMachine:
    transitions: Mapping[ProspectState, frozenset[ProspectState]]

    def __init__(self, transitions: Mapping[ProspectState, frozenset[ProspectState]] | None = None) -> None:
        source = PROSPECT_TRANSITIONS if transitions is None else transitions
        object.__setattr__(self, "transitions", _freeze_table(source, ProspectState))

    def can_transition(self, current: ProspectState, target: ProspectState) -> bool:
        return target in self.transitions.get(current, frozenset()) and target != current

    def validate(self, current: ProspectState, target: ProspectState) -> None:
        if not self.can_transition(current, target):
            raise InvalidDemandTransition(f"Cannot transition from {current.value} to {target.value}")

    def validate_human_resume(
        self,
        current: ProspectState,
        pending_transition: ProspectState | None,
        target: ProspectState,
    ) -> None:
        if current is not ProspectState.NEEDS_HUMAN:
            raise InvalidDemandTransition("validate_human_resume only applies to NEEDS_HUMAN prospects")
        if pending_transition is None:
            raise InvalidDemandTransition("NEEDS_HUMAN prospect has no pending transition to resume")
        if target is not pending_transition:
            raise InvalidDemandTransition(
                f"Human approval target {target.value} does not match "
                f"pending transition {pending_transition.value}"
            )
