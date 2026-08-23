"""Staff dashboard/conversation API (Milestone 8 slice 2): real cases, conversations,
and audit trail, scoped to the authenticated staff user's own business."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.schemas import DashboardCaseSummarySchema
from src.config import Settings
from src.domain.conversations import Conversation, ConversationMessage, ConversationStatus, MessageDirection, MessageRole
from src.domain.models import Lead, ProcessCase, ProcessEvent
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def dashboard_environment(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'dashboard.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    application = create_app(settings=Settings(database_url=database_url, app_env="test"))
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client, factory
    engine.dispose()


def signup_and_login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct horse battery"})
    assert response.status_code == 201
    return response.json()["token"]


def seed_case_with_conversation(factory, *, business_id: str, case_id: str, lead_id: str) -> None:
    with factory() as unit_of_work:
        unit_of_work.businesses.add(
            Business(
                business_id,
                business_id,
                NOW,
                NOW,
                plan="starter",
                subscription_status="active",
            )
        )
        unit_of_work.leads.add(
            business_id,
            Lead(lead_id, name="Ada Lovelace", email="ada@example.com", phone="+13125550100"),
            NOW,
        )
        case = ProcessCase(case_id, business_id, unit_of_work.leads.get(business_id, lead_id), ProcessState.NEEDS_HUMAN, NOW, NOW)
        case.record(ProcessEvent("TRIGGER_RECEIVED", occurred_at=NOW, payload={"channel": "web_chat"}))
        case.record(ProcessEvent("STATE_CHANGED", occurred_at=NOW, payload={"from": "NEW_LEAD", "to": "NEEDS_HUMAN"}))
        unit_of_work.cases.add(case)
        unit_of_work.events.add_many(business_id, case_id, case.event_history)
        # Real callers (ConversationService) never hit this ordering hazard: every
        # write here is interleaved with SELECTs (get_by_external_id, next_sequence,
        # ...) that trigger SQLAlchemy's autoflush and so persist each layer before
        # the next is added. This helper only calls .add(), so without an explicit
        # flush a single end-of-function commit() has no relationship()-based
        # dependency info to order the INSERTs by and can emit conversation_messages
        # before its parent conversation row exists -- FOREIGN KEY constraint failed.
        unit_of_work.session.flush()

        conversation = Conversation(
            conversation_id="conv-1",
            business_id=business_id,
            token_hash="a" * 64,
            channel="web_chat",
            status=ConversationStatus.HUMAN_TAKEOVER_REQUESTED,
            created_at=NOW,
            updated_at=NOW,
            last_activity_at=NOW,
            token_expires_at=NOW.replace(year=NOW.year + 1),
            lead_id=lead_id,
            case_id=case_id,
        )
        unit_of_work.conversations.add(conversation)
        unit_of_work.session.flush()
        unit_of_work.conversation_messages.add(
            ConversationMessage(
                message_id="msg-1",
                business_id=business_id,
                conversation_id="conv-1",
                sequence_number=1,
                direction=MessageDirection.INBOUND,
                role=MessageRole.CUSTOMER,
                text="Hi, my furnace is rattling",
                created_at=NOW,
            )
        )
        unit_of_work.commit()


def link_business(factory, *, business_id: str, user_id: str) -> None:
    """The lightest path to a staff user with a business: write it directly rather
    than going through the full onboarding wizard, which this test doesn't need."""
    with factory() as unit_of_work:
        if unit_of_work.businesses.get(business_id) is None:
            unit_of_work.businesses.add(
                Business(
                    business_id,
                    business_id,
                    NOW,
                    NOW,
                    plan="starter",
                    subscription_status="active",
                )
            )
            unit_of_work.session.flush()
        user = unit_of_work.staff_users.get(user_id)
        unit_of_work.staff_users.save(user.with_business(business_id))
        unit_of_work.commit()


def test_case_summary_exposes_human_readable_service_category() -> None:
    case = ProcessCase(
        "case-category",
        "biz-1",
        Lead("lead-category", name="Ada"),
        ProcessState.QUALIFYING,
        NOW,
        NOW,
    )
    case.record(
        ProcessEvent(
            "QUALIFICATION_EVALUATED",
            occurred_at=NOW,
            payload={"service_id": "drain-cleaning"},
        )
    )

    summary = DashboardCaseSummarySchema.from_domain(
        case,
        service_names={"drain-cleaning": "Drain cleaning"},
    )

    assert summary.category == "Drain cleaning"


def test_case_summary_exposes_latest_non_sensitive_escalation_reason() -> None:
    case = ProcessCase(
        "case-escalation",
        "biz-1",
        Lead("lead-escalation", name="Ada"),
        ProcessState.NEEDS_HUMAN,
        NOW,
        NOW,
    )
    case.record(ProcessEvent(
        "QUALIFICATION_EVALUATED",
        occurred_at=NOW,
        payload={"escalation_reason": "low_confidence"},
    ))

    summary = DashboardCaseSummarySchema.from_domain(case)

    assert summary.escalation_reason == "low_confidence"


def test_staff_can_record_escalation_feedback_in_audit_trail(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "feedback-owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(
        factory, business_id="biz-feedback", case_id="case-feedback", lead_id="lead-feedback"
    )
    link_business(factory, business_id="biz-feedback", user_id=me["user_id"])

    response = client.post(
        "/api/v1/businesses/biz-feedback/conversations/conv-1/escalation-feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={"outcome": "unnecessary"},
    )

    assert response.status_code == 200
    detail = client.get(
        "/api/v1/businesses/biz-feedback/cases/case-feedback",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    feedback = [
        event for event in detail["events"]
        if event["event_type"] == "ESCALATION_FEEDBACK_RECORDED"
    ]
    assert len(feedback) == 1
    assert feedback[0]["payload"]["outcome"] == "unnecessary"


def test_dashboard_analytics_uses_audit_events_and_median_first_response(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "analytics-owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(
        factory, business_id="biz-analytics", case_id="case-analytics", lead_id="lead-analytics"
    )
    link_business(factory, business_id="biz-analytics", user_id=me["user_id"])
    with factory() as unit_of_work:
        unit_of_work.events.add(
            "biz-analytics",
            "case-analytics",
            ProcessEvent(
                "QUALIFICATION_EVALUATED",
                occurred_at=NOW,
                payload={"requires_human": True, "escalation_reason": "ai_review"},
            ),
        )
        unit_of_work.events.add(
            "biz-analytics",
            "case-analytics",
            ProcessEvent("BOOKING_CREATED", occurred_at=NOW),
        )
        unit_of_work.conversation_messages.add(ConversationMessage(
            message_id="msg-analytics-outbound",
            business_id="biz-analytics",
            conversation_id="conv-1",
            sequence_number=2,
            direction=MessageDirection.OUTBOUND,
            role=MessageRole.ASSISTANT,
            text="How can we help?",
            created_at=NOW + timedelta(seconds=5),
        ))
        unit_of_work.commit()

    response = client.get(
        "/api/v1/businesses/biz-analytics/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "total_cases": 1,
        "booked_cases": 1,
        "escalated_cases": 1,
        "lost_cases": 0,
        "booking_conversion_rate": 1.0,
        "escalation_rate": 1.0,
        "lost_rate": 0.0,
        "median_first_response_seconds": 5.0,
        "response_samples": 1,
    }


def test_list_cases_returns_seeded_case(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(factory, business_id="biz-1", case_id="case-1", lead_id="lead-1")
    link_business(factory, business_id="biz-1", user_id=me["user_id"])

    response = client.get("/api/v1/businesses/biz-1/cases", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["cases"]) == 1
    case = body["cases"][0]
    assert case["case_id"] == "case-1"
    assert case["current_state"] == "NEEDS_HUMAN"
    assert case["lead"]["name"] == "Ada Lovelace"
    assert case["event_count"] == 2


def test_case_detail_includes_event_history(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(factory, business_id="biz-1", case_id="case-1", lead_id="lead-1")
    link_business(factory, business_id="biz-1", user_id=me["user_id"])

    response = client.get("/api/v1/businesses/biz-1/cases/case-1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["events"]) == 2
    assert {e["event_type"] for e in body["events"]} == {"TRIGGER_RECEIVED", "STATE_CHANGED"}


def test_conversation_detail_includes_messages_and_case_state(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(factory, business_id="biz-1", case_id="case-1", lead_id="lead-1")
    link_business(factory, business_id="biz-1", user_id=me["user_id"])

    response = client.get(
        "/api/v1/businesses/biz-1/conversations/conv-1", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation"]["case_state"] == "NEEDS_HUMAN"
    assert body["conversation"]["lead_name"] == "Ada Lovelace"
    assert body["conversation"]["lead_phone"] == "+13125550100"
    assert body["conversation"]["lead_email"] == "ada@example.com"
    assert len(body["messages"]) == 1
    assert body["messages"][0]["text"] == "Hi, my furnace is rattling"


def test_dashboard_endpoints_reject_other_business(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(factory, business_id="biz-1", case_id="case-1", lead_id="lead-1")
    link_business(factory, business_id="biz-2", user_id=me["user_id"])

    response = client.get("/api/v1/businesses/biz-1/cases", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_dashboard_endpoints_require_auth(dashboard_environment) -> None:
    client, factory = dashboard_environment
    seed_case_with_conversation(factory, business_id="biz-1", case_id="case-1", lead_id="lead-1")

    response = client.get("/api/v1/businesses/biz-1/cases")
    assert response.status_code == 401
