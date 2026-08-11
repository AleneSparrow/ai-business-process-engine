"""Core domain types for the process engine."""

from .events import EventType
from .models import Action, ActionResult, Decision, Lead, ProcessCase, ProcessEvent
from .states import ProcessState
from .qualification import (
    CustomerResponse,
    IncomingMessage,
    IntentResult,
    LeadIntakeResult,
    MissingInformationResult,
    QualificationResult,
    Urgency,
)

__all__ = [
    "Action",
    "ActionResult",
    "Decision",
    "EventType",
    "Lead",
    "ProcessCase",
    "ProcessEvent",
    "ProcessState",
    "CustomerResponse",
    "IncomingMessage",
    "IntentResult",
    "LeadIntakeResult",
    "MissingInformationResult",
    "QualificationResult",
    "Urgency",
]
