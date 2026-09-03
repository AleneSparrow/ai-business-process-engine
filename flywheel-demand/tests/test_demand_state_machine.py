import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from src.demand.domain.marketing_dna import MarketingOnboardingInput, build_marketing_dna
from src.demand.domain.state_machine import (
    CAMPAIGN_TRANSITIONS,
    PROSPECT_TRANSITIONS,
    CampaignStateMachine,
    InvalidDemandTransition,
    ProspectStateMachine,
)
from src.demand.domain.states import CampaignState, ProspectState


ROOT = Path(__file__).resolve().parents[1]


def test_campaign_happy_path_to_live() -> None:
    machine = CampaignStateMachine()
    machine.validate(CampaignState.MARKET_ANALYSIS, CampaignState.SEGMENTS_READY)
    machine.validate(CampaignState.SEGMENTS_READY, CampaignState.POSITIONED)
    machine.validate(CampaignState.POSITIONED, CampaignState.MOTION_SELECTED)
    machine.validate(CampaignState.MOTION_SELECTED, CampaignState.ASSETS_READY)
    machine.validate(CampaignState.ASSETS_READY, CampaignState.LIVE)


def test_campaign_cannot_skip_positioning() -> None:
    with pytest.raises(InvalidDemandTransition, match="MARKET_ANALYSIS to LIVE"):
        CampaignStateMachine().validate(CampaignState.MARKET_ANALYSIS, CampaignState.LIVE)


def test_campaign_human_escalation_has_no_static_exit() -> None:
    machine = CampaignStateMachine()
    assert machine.transitions[CampaignState.NEEDS_HUMAN] == frozenset()
    machine.validate_human_resume(CampaignState.NEEDS_HUMAN, CampaignState.LIVE, CampaignState.LIVE)
    assert not machine.can_transition(CampaignState.NEEDS_HUMAN, CampaignState.LIVE)


def test_prospect_skip_ahead_from_first_touch_to_inquiry() -> None:
    machine = ProspectStateMachine()
    machine.validate(ProspectState.UNKNOWN, ProspectState.INQUIRED)
    machine.validate(ProspectState.INQUIRED, ProspectState.HANDED_OFF)
    assert not machine.can_transition(ProspectState.UNKNOWN, ProspectState.HANDED_OFF)
    assert not machine.can_transition(ProspectState.HANDED_OFF, ProspectState.AWARE)


def test_suppressed_prospect_may_only_return_via_new_opt_in() -> None:
    machine = ProspectStateMachine()
    machine.validate(ProspectState.SUPPRESSED, ProspectState.SUBSCRIBED)
    assert not machine.can_transition(ProspectState.SUPPRESSED, ProspectState.NURTURING)


def test_yaml_campaign_workflow_matches_python() -> None:
    with (ROOT / "workflows" / "campaign_setup.yaml").open(encoding="utf-8") as file:
        workflow = yaml.safe_load(file)
    yaml_transitions = {
        CampaignState(state): frozenset(CampaignState(target) for target in targets)
        for state, targets in workflow["states"].items()
    }
    assert workflow["initial_state"] == CampaignState.MARKET_ANALYSIS.value
    assert yaml_transitions == CAMPAIGN_TRANSITIONS


def test_yaml_prospect_workflow_matches_python() -> None:
    with (ROOT / "workflows" / "attract_to_inquiry.yaml").open(encoding="utf-8") as file:
        workflow = yaml.safe_load(file)
    yaml_transitions = {
        ProspectState(state): frozenset(ProspectState(target) for target in targets)
        for state, targets in workflow["states"].items()
    }
    assert workflow["initial_state"] == ProspectState.UNKNOWN.value
    assert yaml_transitions == PROSPECT_TRANSITIONS


def test_marketing_dna_example_and_builder_output_validate() -> None:
    schema = json.loads((ROOT / "config" / "marketing_dna.schema.json").read_text(encoding="utf-8"))
    example = json.loads((ROOT / "config" / "marketing_dna.example.json").read_text(encoding="utf-8"))
    business = json.loads((ROOT / "config" / "business_dna.example.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(example)
    compiled = build_marketing_dna(
        business,
        MarketingOnboardingInput(physical_postal_address="123 W Lake St, Chicago, IL 60601"),
    )
    validator.validate(compiled)
    assert compiled["handoff"]["entry_state"] == "NEW_LEAD"
    assert compiled["handoff"]["source"] == "flywheel_demand"
