"""Demand-generation engine: strategy, content, loyalty sequences, handoff."""

from .acquisition_engine import AcquisitionEngine, AcquisitionResult
from .claim_guard import UnsubstantiatedClaimError, assert_publishable
from .consent_gate import ComplianceFooterError, ConsentRequiredError
from .content_planner import compile_content_plan, render_article
from .handoff_adapter import DemandHandoffAdapter
from .sequence_planner import compile_welcome_sequence, render_step
from .strategy_service import CampaignNotReadyError, StrategyService

__all__ = [
    "AcquisitionEngine",
    "AcquisitionResult",
    "CampaignNotReadyError",
    "ComplianceFooterError",
    "ConsentRequiredError",
    "DemandHandoffAdapter",
    "StrategyService",
    "UnsubstantiatedClaimError",
    "assert_publishable",
    "compile_content_plan",
    "compile_welcome_sequence",
    "render_article",
    "render_step",
]
