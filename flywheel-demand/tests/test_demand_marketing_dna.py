import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from src.demand.domain.marketing_dna import MarketingOnboardingInput, ProofClaimInput, build_marketing_dna
from src.demand.engine.claim_guard import UnsubstantiatedClaimError, assert_publishable
from src.demand.engine.content_planner import compile_content_plan, render_article
from src.demand.engine.sequence_planner import compile_welcome_sequence
from src.demand.engine.strategy_service import CampaignNotReadyError, StrategyService
from src.demand.domain.states import CampaignState


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "config" / "marketing_dna.schema.json").read_text(encoding="utf-8"))


def example_business_dna() -> dict:
    return json.loads((ROOT / "config" / "business_dna.example.json").read_text(encoding="utf-8"))


def test_zero_config_marketing_dna_uses_only_business_facts() -> None:
    dna = build_marketing_dna(example_business_dna())
    Draft202012Validator(SCHEMA).validate(dna)
    texts = [claim["text"] for claim in dna["positioning"]["claims"]]
    assert any("Acme Home Services offers" in text for text in texts)
    assert any("ZIPs 60601, 60602" in text for text in texts)
    assert dna["targeting"]["strategy"] == "concentrated"
    assert "best" not in dna["positioning"]["statement"].casefold()


def test_owner_proof_is_included_only_when_substantiated() -> None:
    dna = build_marketing_dna(
        example_business_dna(),
        MarketingOnboardingInput(
            proof_claims=(ProofClaimInput(
                text="Ninety percent of booked diagnostic visits started from an online inquiry last quarter.",
                evidence="Internal booking log, Q2 2026, n=40.",
            ),),
        ),
    )
    proof = next(claim for claim in dna["positioning"]["claims"] if claim["id"] == "owner-1")
    assert proof["status"] == "approved"
    assert dna["sequences"]["welcome"]["include_proof_step"] is True
    steps = compile_welcome_sequence(dna)
    assert any(step.purpose == "proof" for step in steps)


def test_sequence_skips_proof_when_owner_supplied_none() -> None:
    steps = compile_welcome_sequence(build_marketing_dna(example_business_dna()))
    assert [step.purpose for step in steps] == [
        "deliver_promise",
        "brand_fit",
        "value",
        "soft_offer",
    ]


def test_unsubstantiated_superlative_cannot_be_published() -> None:
    dna = build_marketing_dna(example_business_dna())
    with pytest.raises(UnsubstantiatedClaimError, match="best"):
        assert_publishable("We are the best plumber in Chicago.", dna)


def test_approved_catalog_claim_is_publishable() -> None:
    dna = build_marketing_dna(example_business_dna())
    claim = dna["positioning"]["claims"][0]["text"]
    assert_publishable(claim, dna)


def test_strategy_service_stops_at_assets_ready_until_address_and_approval() -> None:
    service = StrategyService()
    campaign = service.compile(example_business_dna())
    assert campaign.current_state is CampaignState.ASSETS_READY
    with pytest.raises(CampaignNotReadyError, match="postal address"):
        service.approve_live(campaign, approved_by="owner@example.com")

    ready = service.compile(
        example_business_dna(),
        MarketingOnboardingInput(physical_postal_address="123 W Lake St, Chicago, IL 60601"),
    )
    live = service.approve_live(ready, approved_by="owner@example.com")
    assert live.current_state is CampaignState.LIVE
    assert compile_content_plan(live.marketing_dna)
    article = render_article(compile_content_plan(live.marketing_dna)[0], live.marketing_dna)
    assert "Diagnostic visit".casefold() in article.casefold()
    assert_publishable(article, live.marketing_dna)


def test_attract_only_campaign_can_go_live_without_mailing_address() -> None:
    campaign = StrategyService().compile(
        example_business_dna(),
        MarketingOnboardingInput(loyalty_enabled=False),
    )
    live = StrategyService().approve_live(campaign, approved_by="owner@example.com")
    assert live.current_state is CampaignState.LIVE
    assert compile_welcome_sequence(live.marketing_dna) == ()


def test_builder_has_no_industry_branch_across_verticals() -> None:
    verticals = (
        ("Financial planning", "Retirement planning"),
        ("Legal services", "Initial consultation"),
        ("HVAC", "HVAC diagnostic"),
        ("Education", "Tutoring assessment"),
        ("Wholesale sales", "Wholesale account"),
    )
    for industry, service in verticals:
        business = {
            "business": {
                "id": f"biz-{industry.split()[0].casefold()}",
                "name": f"{industry} Co",
                "industry": industry,
                "description": "",
                "timezone": "America/New_York",
                "currency": "USD",
            },
            "services": [{"name": service, "description": service}],
            "service_areas": [{"id": "primary", "type": "postal_codes", "values": ["10001"]}],
            "communication": {"language": "English", "tone": "friendly, direct, and concise"},
        }
        dna = build_marketing_dna(business)
        Draft202012Validator(SCHEMA).validate(dna)
        assert dna["handoff"]["entry_state"] == "NEW_LEAD"
        assert industry.casefold() in dna["market"]["category"].casefold()
        assert service in dna["market"]["jobs"]
