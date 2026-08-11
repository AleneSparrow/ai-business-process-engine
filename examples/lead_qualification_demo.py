"""Run a two-message Lead Intake and Qualification example without external APIs."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.qualification import IncomingMessage, IntentResult, Urgency  # noqa: E402
from src.engine.intent_extractor import DeterministicIntentExtractor  # noqa: E402
from src.engine.lead_intake import LeadIntakeService  # noqa: E402
from src.engine.question_generator import DeterministicQuestionGenerator  # noqa: E402


def main() -> None:
    with (PROJECT_ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        business_dna = json.load(file)

    extractor = DeterministicIntentExtractor({
        "demo-1": IntentResult(
            service_requested="diagnostic-visit",
            urgency=Urgency.NORMAL,
            customer_location="60601",
            notes="I need a diagnostic plumbing visit in 60601.",
            confidence=0.96,
        ),
        "demo-2": IntentResult(confidence=0.96),
    })
    intake = LeadIntakeService(
        business_dna,
        extractor,
        DeterministicQuestionGenerator(),
    )
    now = datetime.now(timezone.utc)

    first = intake.receive(IncomingMessage(
        business_id="acme-home-services",
        channel="sms",
        external_message_id="demo-1",
        customer_name="Ada",
        phone=None,
        raw_text="I need a diagnostic plumbing visit in 60601.",
        timestamp=now,
    ))
    print(f"Customer: I need a diagnostic plumbing visit in 60601.")
    print(f"State: {first.current_state.value}")
    print(f"System: {first.response.message_text if first.response else '(no question)'}")

    second = intake.receive(IncomingMessage(
        business_id="acme-home-services",
        channel="sms",
        external_message_id="demo-2",
        customer_name="Ada",
        phone="+1 312 555 0100",
        raw_text="You can reach me at +1 312 555 0100.",
        timestamp=now,
        case_id=first.case_id,
    ))
    print("Customer: You can reach me at +1 312 555 0100.")
    print(f"Same case: {second.case_id == first.case_id}")
    print(f"State: {second.current_state.value}")
    print(f"Qualified: {second.qualification.qualified}")


if __name__ == "__main__":
    main()
