"""Demand-generation domain types."""

from .claims import Claim, ClaimStatus, SubstantiationKind
from .consent import ConsentAction, ConsentChannel, ConsentRecord
from .events import CampaignEventType, ProspectEventType
from .handoff import InquiryHandoff
from .models import (
    Campaign,
    CampaignEvent,
    ContentBrief,
    OutboundMessage,
    Prospect,
    ProspectEvent,
    SequenceStep,
)
from .state_machine import (
    CampaignStateMachine,
    InvalidDemandTransition,
    ProspectStateMachine,
)
from .states import CampaignState, ProspectState

__all__ = [
    "Campaign",
    "CampaignEvent",
    "CampaignEventType",
    "CampaignState",
    "CampaignStateMachine",
    "Claim",
    "ClaimStatus",
    "ConsentAction",
    "ConsentChannel",
    "ConsentRecord",
    "ContentBrief",
    "InquiryHandoff",
    "InvalidDemandTransition",
    "OutboundMessage",
    "Prospect",
    "ProspectEvent",
    "ProspectEventType",
    "ProspectState",
    "ProspectStateMachine",
    "SequenceStep",
    "SubstantiationKind",
]
