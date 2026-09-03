from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from src.demand.domain.consent import ConsentChannel
from src.demand.domain.events import ProspectEventType
from src.demand.domain.marketing_dna import MarketingOnboardingInput, ProofClaimInput
from src.demand.domain.models import Prospect, ProspectEvent
from src.demand.domain.states import CampaignState, ProspectState
from src.demand.engine.acquisition_engine import AcquisitionEngine
from src.demand.engine.consent_gate import ConsentRequiredError
from src.demand.engine.strategy_service import StrategyService

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def business_dna() -> dict:
    return json.loads((ROOT / "config" / "business_dna.example.json").read_text(encoding="utf-8"))


def live_campaign(**changes: object):
    extras = MarketingOnboardingInput(
        physical_postal_address="123 W Lake St, Chicago, IL 60601",
        **changes,
    )
    service = StrategyService()
    campaign = service.compile(business_dna(), extras, campaign_id="camp-1")
    return service.approve_live(campaign, approved_by="owner@example.com")


def prospect() -> Prospect:
    return Prospect(
        prospect_id="prospect-1",
        business_id="acme-home-services",
        campaign_id="camp-1",
        created_at=NOW,
        updated_at=NOW,
    )


def test_attract_path_from_view_to_process_engine_handoff() -> None:
    campaign = live_campaign()
    engine = AcquisitionEngine()
    person = prospect()

    viewed = engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.CONTENT_VIEWED.value,
        payload={"brief_id": "problem"},
        occurred_at=NOW,
    ))
    assert viewed.state is ProspectState.AWARE

    engaged = engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.CONTENT_ENGAGED.value,
        payload={"brief_id": "fit"},
        occurred_at=NOW,
    ))
    assert engaged.state is ProspectState.ENGAGED

    result = engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.INQUIRY_RECEIVED.value,
        payload={
            "channel": "webchat",
            "message": "I need a diagnostic plumbing visit in 60601",
            "name": "Ada",
            "phone": "+13125550100",
            "brief_id": "next-step",
        },
        occurred_at=NOW,
    ))
    assert result.state is ProspectState.HANDED_OFF
    assert result.handoff is not None
    assert result.handoff.entry_state == "NEW_LEAD"
    assert result.handoff.source == "flywheel_demand"
    payload = result.handoff.to_intake_payload()
    assert payload["external_message_id"].startswith("demand:")
    assert payload["raw_text"] == "I need a diagnostic plumbing visit in 60601"
    assert payload["source"] == "flywheel_demand"


def test_loyalty_sequence_requires_opt_in_and_can_spam_footer() -> None:
    campaign = live_campaign()
    engine = AcquisitionEngine()
    person = prospect()

    with pytest.raises(ConsentRequiredError):
        engine.send_due_step(campaign, person, now=NOW)

    engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.OPT_IN_RECORDED.value,
        payload={
            "channel": ConsentChannel.EMAIL.value,
            "source": "website_form",
            "email": "ada@example.com",
            "name": "Ada",
        },
        occurred_at=NOW,
    ))
    assert person.has_active_consent(ConsentChannel.EMAIL)

    sent = engine.send_due_step(campaign, person, now=NOW)
    assert sent.outbound is not None
    assert "123 W Lake St, Chicago, IL 60601" in sent.outbound.body
    assert "unsubscribe" in sent.outbound.body.casefold()
    assert sent.state is ProspectState.NURTURING

    later = engine.send_due_step(campaign, person, now=NOW + timedelta(hours=48))
    assert later.outbound is not None
    assert later.outbound.sequence_index == 2


def test_unsubscribe_blocks_further_sends() -> None:
    campaign = live_campaign()
    engine = AcquisitionEngine()
    person = prospect()
    engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.OPT_IN_RECORDED.value,
        payload={"channel": "email", "source": "form", "email": "ada@example.com"},
        occurred_at=NOW,
    ))
    engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.UNSUBSCRIBED.value,
        payload={"channel": "email", "source": "footer"},
        occurred_at=NOW,
    ))
    assert person.current_state is ProspectState.SUPPRESSED
    assert not person.has_active_consent(ConsentChannel.EMAIL)
    result = engine.send_due_step(campaign, person, now=NOW)
    assert result.outbound is None
    assert result.state is ProspectState.SUPPRESSED


def test_sms_opt_in_requires_written_evidence() -> None:
    campaign = live_campaign()
    engine = AcquisitionEngine()
    person = prospect()
    with pytest.raises(ValueError, match="written-consent"):
        engine.receive(campaign, person, ProspectEvent(
            ProspectEventType.OPT_IN_RECORDED.value,
            payload={"channel": "sms", "source": "checkbox", "phone": "+13125550100"},
            occurred_at=NOW,
        ))

    engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.OPT_IN_RECORDED.value,
        payload={
            "channel": "sms",
            "source": "checkbox",
            "phone": "+13125550100",
            "evidence_id": "checkbox-sms-consent-v1",
        },
        occurred_at=NOW,
    ))
    assert person.has_active_consent(ConsentChannel.SMS)


def test_duplicate_prospect_event_is_ignored() -> None:
    campaign = live_campaign()
    engine = AcquisitionEngine()
    person = prospect()
    event = ProspectEvent(
        ProspectEventType.CONTENT_VIEWED.value,
        event_id="view-1",
        occurred_at=NOW,
    )
    first = engine.receive(campaign, person, event)
    second = engine.receive(campaign, person, event)
    assert first.state is ProspectState.AWARE
    assert second.state is ProspectState.AWARE
    assert person.score == 5


def test_campaign_must_be_live_before_prospect_activity() -> None:
    campaign = StrategyService().compile(
        business_dna(),
        MarketingOnboardingInput(physical_postal_address="123 W Lake St, Chicago, IL 60601"),
        campaign_id="camp-1",
    )
    assert campaign.current_state is CampaignState.ASSETS_READY
    with pytest.raises(Exception, match="LIVE campaign"):
        AcquisitionEngine().receive(
            campaign,
            prospect(),
            ProspectEvent(ProspectEventType.CONTENT_VIEWED.value, occurred_at=NOW),
        )


def test_proof_claims_do_not_change_handoff_boundary() -> None:
    campaign = live_campaign(
        proof_claims=(ProofClaimInput(
            text="Forty diagnostic visits were booked from the website last month.",
            evidence="Staff dashboard export, August 2026.",
        ),),
    )
    assert campaign.marketing_dna["handoff"]["entry_state"] == "NEW_LEAD"
