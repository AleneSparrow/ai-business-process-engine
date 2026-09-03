"""Run Attract and Loyalty Demand paths until an inquiry is ready for Flywheel."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.demand.domain.events import ProspectEventType  # noqa: E402
from src.demand.domain.marketing_dna import MarketingOnboardingInput  # noqa: E402
from src.demand.domain.models import Prospect, ProspectEvent  # noqa: E402
from src.demand.engine.acquisition_engine import AcquisitionEngine  # noqa: E402
from src.demand.engine.strategy_service import StrategyService  # noqa: E402


def main() -> None:
    business_dna = json.loads((PROJECT_ROOT / "config" / "business_dna.example.json").read_text(encoding="utf-8"))
    campaign = StrategyService().compile(
        business_dna,
        MarketingOnboardingInput(physical_postal_address="123 W Lake St, Chicago, IL 60601"),
        campaign_id="demo-campaign",
    )
    campaign = StrategyService().approve_live(campaign, approved_by="owner@example.com")
    print(f"Campaign: {campaign.current_state.value}")
    print(f"Positioning: {campaign.marketing_dna['positioning']['statement']}")

    engine = AcquisitionEngine()
    person = Prospect(
        prospect_id="demo-prospect",
        business_id="acme-home-services",
        campaign_id="demo-campaign",
    )
    now = datetime.now(timezone.utc)
    engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.CONTENT_VIEWED.value,
        payload={"brief_id": "problem"},
        occurred_at=now,
    ))
    engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.OPT_IN_RECORDED.value,
        payload={"channel": "email", "source": "article-form", "email": "ada@example.com", "name": "Ada"},
        occurred_at=now,
    ))
    sent = engine.send_due_step(campaign, person, now=now)
    print(f"Prospect after welcome: {person.current_state.value}")
    if sent.outbound:
        print("Welcome email sent with CAN-SPAM footer.")

    result = engine.receive(campaign, person, ProspectEvent(
        ProspectEventType.INQUIRY_RECEIVED.value,
        payload={
            "channel": "webchat",
            "message": "I need a diagnostic plumbing visit in 60601",
            "name": "Ada",
            "phone": "+13125550100",
            "email": "ada@example.com",
        },
        occurred_at=now,
    ))
    print(f"Prospect after inquiry: {result.state.value}")
    assert result.handoff is not None
    payload = result.handoff.to_intake_payload()
    print(f"Handoff source: {payload['source']}")
    print(f"Handoff entry: {payload['entry_state']}")
    print("Flywheel receives this JSON at POST /api/v1/businesses/{id}/demand/inquiries")


if __name__ == "__main__":
    main()
