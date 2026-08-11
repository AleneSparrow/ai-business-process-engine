"""Event names used in process-case audit history."""

from enum import StrEnum


class EventType(StrEnum):
    TRIGGER_RECEIVED = "TRIGGER_RECEIVED"
    DECISION_RECORDED = "DECISION_RECORDED"
    STATE_CHANGED = "STATE_CHANGED"
    TRANSITION_REJECTED = "TRANSITION_REJECTED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
