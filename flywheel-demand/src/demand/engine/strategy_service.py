"""Compile a campaign from Business DNA and walk the strategy funnel with rules."""

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from src.demand.domain.events import CampaignEventType
from src.demand.domain.marketing_dna import MarketingOnboardingInput, build_marketing_dna
from src.demand.domain.models import Campaign, CampaignEvent
from src.demand.domain.state_machine import CampaignStateMachine, InvalidDemandTransition
from src.demand.domain.states import CampaignState
from src.demand.engine.content_planner import compile_content_plan
from src.demand.engine.sequence_planner import compile_welcome_sequence


class CampaignNotReadyError(ValueError):
    """The campaign cannot go live until compliance and assets are in place."""


_SETUP_PATH = (
    CampaignState.SEGMENTS_READY,
    CampaignState.POSITIONED,
    CampaignState.MOTION_SELECTED,
    CampaignState.ASSETS_READY,
)


class StrategyService:
    """Deterministic audience → positioning → assets compiler."""

    def __init__(self, state_machine: CampaignStateMachine | None = None) -> None:
        self.state_machine = state_machine or CampaignStateMachine()

    def compile(
        self,
        business_dna: Mapping[str, Any],
        onboarding: MarketingOnboardingInput | None = None,
        *,
        campaign_id: str | None = None,
    ) -> Campaign:
        dna = build_marketing_dna(business_dna, onboarding)
        campaign = Campaign(
            campaign_id=campaign_id or str(uuid4()),
            business_id=str(dna["business_id"]),
            marketing_dna=dna,
            current_state=CampaignState.MARKET_ANALYSIS,
        )
        campaign.record(CampaignEvent(
            CampaignEventType.MARKETING_DNA_COMPILED,
            payload={"business_id": campaign.business_id},
        ))
        for target in _SETUP_PATH:
            self._advance(campaign, target, f"Compiled {target.value} from Business DNA")
        briefs = compile_content_plan(campaign.marketing_dna)
        steps = compile_welcome_sequence(campaign.marketing_dna)
        campaign.record(CampaignEvent(
            CampaignEventType.ASSETS_COMPILED,
            payload={"briefs": len(briefs), "sequence_steps": len(steps)},
        ))
        return campaign

    def approve_live(self, campaign: Campaign, *, approved_by: str) -> Campaign:
        if not approved_by.strip():
            raise ValueError("approved_by must not be empty")
        if campaign.current_state is CampaignState.NEEDS_HUMAN:
            self.state_machine.validate_human_resume(
                campaign.current_state,
                campaign.pending_transition,
                CampaignState.LIVE,
            )
        else:
            self.state_machine.validate(campaign.current_state, CampaignState.LIVE)
        self._assert_liveable(campaign)
        campaign.record(CampaignEvent(
            CampaignEventType.CAMPAIGN_APPROVED,
            payload={"approved_by": approved_by},
        ))
        previous = campaign.current_state
        campaign._apply_transition(CampaignState.LIVE)
        campaign.record(CampaignEvent(
            CampaignEventType.STATE_CHANGED,
            payload={"from": previous.value, "to": CampaignState.LIVE.value},
        ))
        return campaign

    def pause(self, campaign: Campaign) -> Campaign:
        self._advance(campaign, CampaignState.PAUSED, "Campaign paused")
        return campaign

    def _advance(self, campaign: Campaign, target: CampaignState, reason: str) -> None:
        self.state_machine.validate(campaign.current_state, target)
        previous = campaign.current_state
        campaign.record(CampaignEvent(
            CampaignEventType.DECISION_RECORDED,
            payload={"decision_type": "RULE", "reason": reason, "target_state": target.value},
        ))
        campaign._apply_transition(target)
        campaign.record(CampaignEvent(
            CampaignEventType.STATE_CHANGED,
            payload={"from": previous.value, "to": target.value},
        ))

    def _assert_liveable(self, campaign: Campaign) -> None:
        dna = campaign.marketing_dna
        motions = dna.get("motions") or {}
        if not motions.get("attract") and not motions.get("loyalty"):
            raise CampaignNotReadyError("a live campaign needs attract and/or loyalty")
        if motions.get("loyalty"):
            address = str((dna.get("compliance") or {}).get("physical_postal_address") or "").strip()
            if not address:
                raise CampaignNotReadyError(
                    "loyalty email cannot go live without a physical postal address (CAN-SPAM)"
                )
            if not compile_welcome_sequence(dna):
                raise CampaignNotReadyError("loyalty motion is enabled but no sequence compiled")
        if motions.get("attract") and not compile_content_plan(dna):
            raise CampaignNotReadyError("attract motion is enabled but no content plan compiled")


def require_live(campaign: Campaign) -> None:
    if campaign.current_state is not CampaignState.LIVE:
        raise InvalidDemandTransition(
            f"prospect activity requires a LIVE campaign, not {campaign.current_state.value}"
        )
