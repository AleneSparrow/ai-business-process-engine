import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.api.app import create_app
from src.config import Settings
from src.domain.qualification import IncomingMessage, IntentResult
from src.domain.tenancy import Business
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.persistence.sqlalchemy_models import Base, ProcessedMessageRow, ProcessEventRow
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine
from src.persistence.auth_service import AuthService


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 11, 8, 0, tzinfo=timezone.utc)


def load_dna(business_id: str) -> dict:
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        configuration = json.load(file)
    configuration["business"]["id"] = business_id
    configuration["business"]["name"] = business_id
    return configuration


def seed_business(factory, business_id: str) -> None:
    with factory() as unit_of_work:
        unit_of_work.businesses.add(Business(business_id, business_id, NOW, NOW))
        unit_of_work.business_dna.add_version(business_id, load_dna(business_id))
        unit_of_work.commit()


@pytest.fixture
def api_environment(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'api.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    seed_business(factory, "tenant-a")
    seed_business(factory, "tenant-b")
    scripted = {
        "valid": IntentResult(
            service_requested="diagnostic-visit", customer_location="60601", confidence=0.95
        ),
        "missing-phone": IntentResult(
            service_requested="diagnostic-visit", customer_location="60601", confidence=0.95
        ),
        "unsupported": IntentResult(
            service_requested="roof-replacement", customer_location="60601", confidence=0.95
        ),
        "low-confidence": IntentResult(confidence=0.2),
        "tenant-a-message": IntentResult(
            service_requested="diagnostic-visit", customer_location="60601", confidence=0.95
        ),
        "tenant-b-message": IntentResult(
            service_requested="diagnostic-visit", customer_location="60601", confidence=0.95
        ),
    }
    application = create_app(
        settings=Settings(database_url=database_url, app_env="test"),
        intent_extractor=DeterministicIntentExtractor(scripted),
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        session = AuthService(factory).signup("api-owner@example.com", "correct horse battery")
        with factory() as unit_of_work:
            owner = unit_of_work.staff_users.get(session.user.user_id)
            assert owner is not None
            unit_of_work.staff_users.save(owner.with_business("tenant-a").with_business("tenant-b"))
            unit_of_work.commit()
        client.headers.update({"Authorization": f"Bearer {session.token}"})
        yield client, factory
    engine.dispose()


def message_payload(external_message_id: str, **changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "channel": "sms",
        "external_message_id": external_message_id,
        "message": "I need a diagnostic visit in 60601",
        "timestamp": NOW.isoformat(),
        "customer_name": "Ada",
        "phone": "+1 312 555 0100",
    }
    values.update(changes)
    return values


def test_health_and_readiness(api_environment) -> None:
    client, _ = api_environment
    request_id = "test-request-123"
    health = client.get("/health", headers={"X-Request-ID": request_id})
    ready = client.get("/ready")

    assert health.status_code == 200 and health.json() == {"status": "ok"}
    assert health.headers["X-Request-ID"] == request_id
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "dependencies": {"database": "ok", "ai_configuration": "ok"},
    }
    assert logging.getLogger("uvicorn.access").disabled is True


def test_application_startup_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    application = create_app()

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        with TestClient(application):
            pass


def test_unknown_business_returns_404_without_internal_details(api_environment) -> None:
    client, _ = api_environment
    response = client.get("/api/v1/businesses/unknown")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "business_not_found"
    assert "sql" not in response.text.casefold()


def test_business_endpoint_returns_safe_metadata_only(api_environment) -> None:
    client, _ = api_environment
    response = client.get("/api/v1/businesses/tenant-a")

    assert response.status_code == 200
    assert response.json()["business_id"] == "tenant-a"
    assert set(response.json()) == {"business_id", "name", "created_at", "updated_at"}


def test_direct_lead_intake_requires_staff_authentication(api_environment) -> None:
    client, _ = api_environment
    response = client.post(
        "/api/v1/businesses/tenant-a/messages",
        json=message_payload("unauthenticated-intake"),
        headers={"Authorization": ""},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_direct_lead_intake_rejects_staff_user_from_another_tenant(api_environment) -> None:
    client, factory = api_environment
    other_session = AuthService(factory).signup("other-owner@example.com", "correct horse battery")
    with factory() as unit_of_work:
        other_owner = unit_of_work.staff_users.get(other_session.user.user_id)
        assert other_owner is not None
        unit_of_work.staff_users.save(other_owner.with_business("tenant-b"))
        unit_of_work.commit()

    response = client.post(
        "/api/v1/businesses/tenant-a/messages",
        json=message_payload("foreign-tenant-intake"),
        headers={"Authorization": f"Bearer {other_session.token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    ("external_id", "changes", "expected_state", "requires_human"),
    (
        ("valid", {}, "QUALIFIED", False),
        ("missing-phone", {"phone": None}, "QUALIFYING", False),
        ("unsupported", {"message": "I need a roof replacement"}, "LOST", False),
        ("low-confidence", {"message": "I am not sure what I need"}, "QUALIFYING", False),
    ),
)
def test_lead_intake_outcomes(
    api_environment,
    external_id: str,
    changes: dict[str, object],
    expected_state: str,
    requires_human: bool,
) -> None:
    client, _ = api_environment
    response = client.post(
        "/api/v1/businesses/tenant-a/messages",
        json=message_payload(external_id, **changes),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["business_id"] == "tenant-a"
    assert body["current_state"] == expected_state
    assert body["requires_human"] is requires_human
    if expected_state == "QUALIFYING" and external_id == "missing-phone":
        assert body["qualification"]["missing_fields"] == ["phone"]
        assert "phone" in body["customer_response"]["message_text"].casefold()


def test_duplicate_replay_is_stable_and_does_not_duplicate_audit_events(api_environment) -> None:
    client, factory = api_environment
    payload = message_payload("valid")
    first = client.post("/api/v1/businesses/tenant-a/messages", json=payload)
    duplicate = client.post("/api/v1/businesses/tenant-a/messages", json=payload)

    assert first.status_code == duplicate.status_code == 200
    assert first.json()["case_id"] == duplicate.json()["case_id"]
    assert first.json()["current_state"] == duplicate.json()["current_state"]
    assert not first.json()["duplicate"] and duplicate.json()["duplicate"]
    with factory() as unit_of_work:
        assert unit_of_work.session.scalar(
            select(func.count()).select_from(ProcessedMessageRow).where(
                ProcessedMessageRow.business_id == "tenant-a",
                ProcessedMessageRow.external_message_id == "valid",
            )
        ) == 1
        event_count = unit_of_work.session.scalar(
            select(func.count()).select_from(ProcessEventRow).where(
                ProcessEventRow.business_id == "tenant-a",
                ProcessEventRow.case_id == first.json()["case_id"],
            )
        )
        assert event_count == 12


def test_reused_message_identity_with_different_content_returns_409(api_environment) -> None:
    client, _ = api_environment
    first = client.post(
        "/api/v1/businesses/tenant-a/messages", json=message_payload("valid")
    )
    collision = client.post(
        "/api/v1/businesses/tenant-a/messages",
        json=message_payload("valid", message="Different content"),
    )

    assert first.status_code == 200
    assert collision.status_code == 409
    assert collision.json()["error"]["code"] == "idempotency_collision"


def test_tenant_cannot_address_another_tenants_case(api_environment) -> None:
    client, factory = api_environment
    created = client.post(
        "/api/v1/businesses/tenant-a/messages", json=message_payload("tenant-a-message")
    )
    response = client.post(
        "/api/v1/businesses/tenant-b/messages",
        json=message_payload("tenant-b-message", case_id=created.json()["case_id"]),
    )

    assert created.status_code == 200
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "case_not_found"
    with factory() as unit_of_work:
        assert unit_of_work.idempotency.get(
            "tenant-b", "sms", "tenant-b-message"
        ) is None


@pytest.mark.parametrize(
    "changes",
    (
        {"message": ""},
        {"channel": "sms !!!"},
        {"timestamp": "2026-08-11T08:00:00"},
        {"phone": "not-a-phone"},
        {"email": "invalid"},
    ),
)
def test_malformed_requests_return_422(api_environment, changes: dict[str, object]) -> None:
    client, _ = api_environment
    response = client.post(
        "/api/v1/businesses/tenant-a/messages",
        json=message_payload("malformed", **changes),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "traceback" not in response.text.casefold()


def test_tenant_disabled_channel_returns_422(api_environment) -> None:
    client, _ = api_environment
    response = client.post(
        "/api/v1/businesses/tenant-a/messages",
        json=message_payload("disabled-channel", channel="whatsapp"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "message_not_accepted"


def test_openapi_documents_versioned_message_endpoint(api_environment) -> None:
    client, _ = api_environment
    response = client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["info"]["title"] == "AI Business Process Engine API"
    assert "/api/v1/businesses/{business_id}/messages" in document["paths"]
    operation = document["paths"]["/api/v1/businesses/{business_id}/messages"]["post"]
    assert "Staff-authenticated" in operation["description"]
    assert {"401", "403"}.issubset(operation["responses"])


def test_request_body_limit_rejects_oversized_message(api_environment) -> None:
    client, _ = api_environment
    response = client.post(
        "/api/v1/businesses/tenant-a/messages",
        json=message_payload("oversized", message="x" * 70_000),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_request_body_limit_rejects_oversized_chunked_body(api_environment) -> None:
    client, _ = api_environment
    response = client.post(
        "/api/v1/businesses/acme-home-services/lead-intake",
        content=iter((b'{"message":"', b"x" * 70_000, b'"}')),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert response.headers["X-Request-ID"]


class FailingApiExtractor:
    def extract(
        self, message: IncomingMessage, business_dna: Mapping[str, object]
    ) -> IntentResult:
        raise RuntimeError("private provider detail must not escape")


def test_unexpected_error_is_safe_and_logs_no_payload(
    api_environment, caplog: pytest.LogCaptureFixture
) -> None:
    existing_client, _ = api_environment
    database_url = existing_client.app.state.container.settings.database_url
    application = create_app(
        settings=Settings(database_url=database_url, app_env="test"),
        intent_extractor=FailingApiExtractor(),
    )
    secret_message = "customer-private-payload-marker"
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/businesses/tenant-a/messages",
            json=message_payload("unexpected-error", message=secret_message),
            headers={"Authorization": existing_client.headers["Authorization"]},
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "private provider detail" not in response.text
    assert secret_message not in caplog.text
    assert "+1 312 555 0100" not in caplog.text
