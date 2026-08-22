"""Real PostgreSQL concurrency behavior exercised through the HTTP boundary."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select

from src.ai.adapters import AIIntentExtractor
from src.ai.fake_provider import FakeAIProvider
from src.api.app import create_app
from src.config import Settings
from src.domain.events import EventType
from src.domain.tenancy import Business
from src.persistence.sqlalchemy_models import (
    LeadRow,
    ProcessCaseRow,
    ProcessedMessageRow,
    ProcessEventRow,
)
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


pytestmark = pytest.mark.postgresql
ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def postgresql_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url or not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL")
    return url


def test_concurrent_identical_http_requests_have_one_logical_effect(postgresql_url: str) -> None:
    engine = create_database_engine(postgresql_url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    business_id = f"api-concurrency-{uuid4()}"
    external_id = str(uuid4())
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        configuration = json.load(file)
    configuration["business"]["id"] = business_id
    now = datetime.now(timezone.utc)
    with factory() as unit_of_work:
        unit_of_work.businesses.add(Business(business_id, business_id, now, now))
        unit_of_work.business_dna.add_version(business_id, configuration)
        unit_of_work.commit()

    provider = FakeAIProvider([{
        "service_id": "diagnostic-visit",
        "unsupported_service": False,
        "unsupported_service_name": None,
        # Verified verbatim against the posted message below
        # (AIIntentExtractor._resolve_service, src/ai/adapters.py).
        "service_evidence": "diagnostic visit",
        "urgency": "normal",
        "customer_location": "60601",
        "preferred_time": None,
        "notes": "Concurrent customer requests a diagnostic visit.",
        "customer_name": None,
        "phone": None,
        "email": None,
        "confidence": 0.95,
        "requires_human": False,
        "qualification_answers": [],
        # Both required in IntentOutput, no default -- see test_ai.py's
        # intent_output() helper for the same fix and why it's needed.
        "objection_phrase": None,
        "customer_tone": "neutral",
    }])
    application = create_app(
        settings=Settings(database_url=postgresql_url, app_env="test"),
        intent_extractor=AIIntentExtractor(provider),
    )
    payload = {
        "channel": "sms",
        "external_message_id": external_id,
        "message": "I need a diagnostic visit in 60601",
        "timestamp": now.isoformat(),
        "customer_name": "Concurrent HTTP Customer",
        "phone": f"+1{str(uuid4().int)[:10]}",
    }
    start = Barrier(2)
    with TestClient(application, raise_server_exceptions=False) as client:
        def post_concurrently() -> Response:
            start.wait(timeout=10)
            return client.post(f"/api/v1/businesses/{business_id}/messages", json=payload)

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: post_concurrently(), range(2)))

    assert all(response.status_code == 200 for response in responses)
    bodies = [response.json() for response in responses]
    assert len({body["case_id"] for body in bodies}) == 1
    assert len({body["lead_id"] for body in bodies}) == 1
    assert {body["current_state"] for body in bodies} == {"QUALIFIED"}
    assert sum(body["duplicate"] for body in bodies) == 1
    assert provider.call_count == 1

    with factory() as unit_of_work:
        assert unit_of_work.session.scalar(
            select(func.count()).select_from(LeadRow).where(LeadRow.business_id == business_id)
        ) == 1
        assert unit_of_work.session.scalar(
            select(func.count()).select_from(ProcessCaseRow).where(
                ProcessCaseRow.business_id == business_id
            )
        ) == 1
        assert unit_of_work.session.scalar(
            select(func.count()).select_from(ProcessedMessageRow).where(
                ProcessedMessageRow.business_id == business_id
            )
        ) == 1
        intake_events = unit_of_work.session.scalar(
            select(func.count()).select_from(ProcessEventRow).where(
                ProcessEventRow.business_id == business_id,
                ProcessEventRow.event_type == EventType.LEAD_INTAKE_RECEIVED.value,
            )
        )
        assert intake_events == 1
    engine.dispose()
