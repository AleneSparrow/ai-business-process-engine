"""HTTP receiver for Flywheel Demand inquiries at NEW_LEAD."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import Settings
from src.domain.qualification import IntentResult
from src.domain.tenancy import Business
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
SECRET = "demand-task-secret"
EXTERNAL_ID = "demand:prospect-1:event-1"


def load_dna(business_id: str) -> dict:
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        configuration = json.load(file)
    configuration["business"]["id"] = business_id
    configuration["business"]["name"] = business_id
    return configuration


def inquiry_payload(business_id: str, **changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "business_id": business_id,
        "channel": "webchat",
        "external_message_id": EXTERNAL_ID,
        "raw_text": "I need a diagnostic plumbing visit in 60601",
        "timestamp": NOW.isoformat(),
        "customer_name": "Ada",
        "phone": "+13125550100",
        "email": None,
        "sms_consent": False,
        "source": "flywheel_demand",
        "entry_state": "NEW_LEAD",
        "handoff_id": "handoff-1",
        "campaign_id": "camp-1",
        "prospect_id": "prospect-1",
        "attribution": {"brief_id": "next-step"},
    }
    values.update(changes)
    return values


@pytest.fixture
def demand_app(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'demand.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    with factory() as unit_of_work:
        unit_of_work.businesses.add(Business("acme-home-services", "Acme", NOW, NOW))
        unit_of_work.business_dna.add_version("acme-home-services", load_dna("acme-home-services"))
        unit_of_work.commit()
    application = create_app(
        settings=Settings(
            database_url=database_url,
            app_env="test",
            internal_task_secret=SECRET,
        ),
        intent_extractor=DeterministicIntentExtractor({
            EXTERNAL_ID: IntentResult(
                service_requested="diagnostic-visit",
                customer_location="60601",
                confidence=0.95,
            )
        }),
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client, factory
    engine.dispose()


def _activate_demand(factory) -> None:
    with factory() as unit_of_work:
        unit_of_work.businesses.update_demand_billing(
            "acme-home-services",
            payment_customer_id="cus_demand",
            demand_payment_subscription_id="sub_demand",
            demand_subscription_status="active",
            demand_trial_ends_at=None,
            demand_current_period_end=None,
        )
        unit_of_work.commit()


def test_demand_inquiry_requires_internal_secret(demand_app) -> None:
    client, factory = demand_app
    _activate_demand(factory)
    response = client.post(
        "/api/v1/businesses/acme-home-services/demand/inquiries",
        json=inquiry_payload("acme-home-services"),
    )
    assert response.status_code == 401


def test_demand_inquiry_rejected_without_add_on(demand_app) -> None:
    client, _factory = demand_app
    response = client.post(
        "/api/v1/businesses/acme-home-services/demand/inquiries",
        json=inquiry_payload("acme-home-services"),
        headers={"X-Internal-Task-Secret": SECRET},
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "demand_subscription_inactive"


def test_demand_inquiry_opens_new_lead_and_qualifies(demand_app) -> None:
    client, factory = demand_app
    _activate_demand(factory)
    response = client.post(
        "/api/v1/businesses/acme-home-services/demand/inquiries",
        json=inquiry_payload("acme-home-services"),
        headers={"X-Internal-Task-Secret": SECRET},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_state"] == "QUALIFIED"
    assert body["qualification"]["qualified"] is True
    assert body["case_created"] is True


def test_demand_inquiry_rejects_non_new_lead_entry(demand_app) -> None:
    client, factory = demand_app
    _activate_demand(factory)
    response = client.post(
        "/api/v1/businesses/acme-home-services/demand/inquiries",
        json=inquiry_payload("acme-home-services", entry_state="QUALIFIED"),
        headers={"X-Internal-Task-Secret": SECRET},
    )
    assert response.status_code == 422
