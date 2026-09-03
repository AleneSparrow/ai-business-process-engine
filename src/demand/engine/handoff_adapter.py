"""Deliver a Demand inquiry into the Business Process Engine as ordinary intake."""

from __future__ import annotations

from src.demand.domain.handoff import InquiryHandoff
from src.domain.qualification import LeadIntakeResult
from src.engine.lead_intake import LeadIntakeService


class DemandHandoffAdapter:
    """Product boundary. Demand does not qualify, book, quote, or sell."""

    def __init__(self, intake: LeadIntakeService) -> None:
        self.intake = intake

    def deliver(self, handoff: InquiryHandoff) -> LeadIntakeResult:
        if handoff.entry_state.value != "NEW_LEAD":
            raise ValueError("Demand may only hand off into NEW_LEAD")
        return self.intake.receive(handoff.to_incoming_message())
