"""Reproduce "the widget gives the same answer every time" (reported
2026-08-30) against the real API, through the actual public HTTP routes
(same path the widget itself uses), not a lower-level service call.

Root cause found: nothing repeats a *cached* response. Once a case reaches
NEEDS_HUMAN, every following message correctly gets the identical
human-escalation reply -- that IS the right reply for that state. The bug
is reaching NEEDS_HUMAN at all: a business with enforce_service_area=False
whose qualification.rules still only contains an area-keyed rule (e.g. the
onboarding-time {"field": "service_area_id", ...} rule from before it
switched to remote/nationwide) can never match that rule again --
service_area_id is always None once area enforcement is off -- so every
lead silently falls through to qualification.default_outcome
("needs_human") forever, right after the last required field is filled in.

Fixed in BusinessDNASettingsService._apply: switching a business to remote
now appends a {"field": "service_id", "operator": "exists", ...} safety-net
rule whenever no rule already grants "qualified" from service_id, not only
when `rules` was completely empty (see git history for the diff and
tests/test_business_dna_settings.py for the regression coverage). This
script's own DNA below still hand-builds the pre-fix shape (a bare
"metro"-keyed rule with enforce_service_area=False) so it keeps reproducing
the trap for any DNA that predates the fix or was hand-edited around it --
it does not exercise BusinessDNASettingsService itself.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.api.app import create_app  # noqa: E402
from src.config import Settings  # noqa: E402
from src.domain.tenancy import Business  # noqa: E402
from src.engine.qualification_service import QualificationService  # noqa: E402
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine  # noqa: E402
from src.persistence.sqlalchemy_models import Base  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

_original_evaluate = QualificationService.evaluate


def _traced_evaluate(self, lead, intent, business_dna, case_metadata=None):
    result = _original_evaluate(self, lead, intent, business_dna, case_metadata=case_metadata)
    print(
        "    [qualification] intent="
        f"requires_human={intent.requires_human} confidence={intent.confidence} "
        f"unintelligible={intent.unintelligible} urgency={intent.urgency.value} "
        f"service_requested={intent.service_requested!r} customer_location={intent.customer_location!r} "
        f"-> state={result.recommended_next_state.value} reason_codes={result.reason_codes} "
        f"reasons={result.reasons}"
    )
    return result


QualificationService.evaluate = _traced_evaluate

NOW = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
BUSINESS_ID = "widget-repro-law-firm"


def _dna() -> dict:
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        config = json.load(file)
    config["business"]["id"] = BUSINESS_ID
    config["business"]["name"] = "Repro Law Firm"
    config["business"]["industry"] = "legal_services"
    config["business"]["description"] = "Family law practice"
    config["communication"]["channels"] = ["webchat"]
    config["communication"]["default_channel"] = "webchat"
    consultation = dict(config["services"][0])
    consultation.update({
        "id": "consultation", "name": "Consultation", "intake_keywords": ["consultation"],
        "description": "Family, contract, and civil legal consultations",
        "qualification_questions": [],
    })
    config["services"] = [consultation]
    config["qualification"]["enforce_service_area"] = False
    return config


def main() -> None:
    import tempfile
    db_path = Path(tempfile.mktemp(suffix=".db"))
    database_url = f"sqlite+pysqlite:///{db_path}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    with factory() as uow:
        uow.businesses.add(Business(BUSINESS_ID, "Repro Law Firm", NOW, NOW))
        uow.business_dna.add_version(BUSINESS_ID, _dna())
        uow.commit()
    engine.dispose()

    base_settings = Settings.from_environment()
    import dataclasses
    settings = dataclasses.replace(base_settings, database_url=database_url)
    app = create_app(settings=settings)

    messages = [
        "My ex is not following our custody agreement and I need legal help",
        "My name is Sarah Chen",
        "555-201-3344",
        "60601",
    ]

    with TestClient(app, raise_server_exceptions=True) as client:
        token = None
        for index, text in enumerate(messages):
            payload = {"message": text, "external_message_id": f"m{index}"}
            if token is None:
                response = client.post(
                    f"/api/v1/public/businesses/{BUSINESS_ID}/conversations", json=payload,
                )
            else:
                response = client.post(
                    f"/api/v1/public/businesses/{BUSINESS_ID}/conversations/{token}/messages",
                    json=payload,
                )
            print(f"--- turn {index}: {text!r} (status {response.status_code}) ---")
            if response.status_code != 200:
                print(response.text)
                continue
            body = response.json()
            token = body.get("conversation_token", token)
            last_message = body["messages"][-1] if body.get("messages") else None
            print("assistant reply:", last_message["text"] if last_message else None)
            print("current_state:", body.get("current_state"))

    engine.dispose()


if __name__ == "__main__":
    main()
