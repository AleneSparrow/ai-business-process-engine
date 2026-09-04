"""Staff dashboard/conversation API (Milestone 8 slice 2): real cases, conversations,
and audit trail, scoped to the authenticated staff user's own business."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from src.api.app import create_app
from src.api.schemas import DashboardCaseSummarySchema
from src.config import Settings
from src.domain.conversations import Conversation, ConversationMessage, ConversationStatus, MessageDirection, MessageRole
from src.domain.models import Lead, ProcessCase, ProcessEvent
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.sqlalchemy_models import Base, ProcessCaseRow
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
    assert summary.lifecycle_actions == ()


def test_won_case_summary_exposes_payment_and_completion_actions() -> None:
    case = ProcessCase(
        "case-won",
        "biz-1",
        Lead("lead-won", name="Ada"),
        ProcessState.WON,
        NOW,
        NOW,
    )
    summary = DashboardCaseSummarySchema.from_domain(case)
    assert summary.lifecycle_actions == ("record_payment", "mark_completed")


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


def test_case_summary_reconstructs_safe_reason_for_legacy_escalation() -> None:
    case = ProcessCase(
        "case-legacy-escalation",
        "biz-1",
        Lead("lead-legacy-escalation", name="Ada"),
        ProcessState.NEEDS_HUMAN,
        NOW,
        NOW,
    )
    case.record(ProcessEvent(
        "INTENT_EXTRACTED",
        occurred_at=NOW,
        payload={"urgency": "normal", "confidence": 0.42, "service_requested": "consultation"},
    ))
    case.record(ProcessEvent(
        "QUALIFICATION_EVALUATED",
        occurred_at=NOW,
        payload={"requires_human": True, "reasons": ["Human review required"]},
    ))

    summary = DashboardCaseSummarySchema.from_domain(case)

    assert summary.escalation_reason == "low_confidence"


@pytest.mark.parametrize(
    ("legacy_reason", "expected"),
    (
        (
            "Provided contact identity is already associated with another lead; "
            "a person must confirm before continuing",
            "identity_conflict",
        ),
        ("Service area cannot be evaluated deterministically", "service_area_uncertain"),
        ("Configured qualification policy requires human review", "policy_review"),
        ("Case is already awaiting human review", "already_pending"),
    ),
)
def test_legacy_reason_vocabulary_stays_recognised(legacy_reason: str, expected: str) -> None:
    """Pins the frozen substrings in escalation_reason_from_domain.

    Those substrings are matched against reason text already WRITTEN TO EVENT
    HISTORY. Stored events never change, so the matcher must keep speaking the
    vocabulary of the day the event was written -- it must NOT be refactored to
    import today's reason constants, however much tidier that looks.

    Without this test the breakage would be silent: an unrecognised reason
    falls through to "ai_review" rather than raising, so a staff member would
    just see a vaguer category and nobody would know why.
    """
    case = ProcessCase(
        f"case-legacy-{expected}",
        "biz-1",
        Lead(f"lead-legacy-{expected}", name="Ada"),
        ProcessState.NEEDS_HUMAN,
        NOW,
        NOW,
    )
    case.record(ProcessEvent(
        "QUALIFICATION_EVALUATED",
        occurred_at=NOW,
        payload={"requires_human": True, "reasons": [legacy_reason]},
    ))

    summary = DashboardCaseSummarySchema.from_domain(case)

    assert summary.escalation_reason == expected


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
    identity_response = client.post(
        "/api/v1/businesses/biz-feedback/conversations/conv-1/escalation-feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={"outcome": "identity_different_customer"},
    )

    assert response.status_code == 200
    assert identity_response.status_code == 200
    detail = client.get(
        "/api/v1/businesses/biz-feedback/cases/case-feedback",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    feedback = [
        event for event in detail["events"]
        if event["event_type"] == "ESCALATION_FEEDBACK_RECORDED"
    ]
    assert [event["payload"]["outcome"] for event in feedback] == [
        "unnecessary",
        "identity_different_customer",
    ]


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
        unit_of_work.events.add(
            "biz-analytics",
            "case-analytics",
            ProcessEvent(
                "ESCALATION_FEEDBACK_RECORDED",
                occurred_at=NOW,
                payload={"outcome": "unnecessary"},
            ),
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
        "escalation_reasons": {"ai_review": 1},
        "escalation_feedback": {
            "unnecessary": 1,
            "missed": 0,
            "wrong_service": 0,
            "identity_same_customer": 0,
            "identity_different_customer": 0,
        },
        "hidden_test_cases": 0,
        "hidden_test_conversations": 0,
        "includes_test_data": False,
        "stats_since": None,
        "period_start": None,
        "period_end": None,
    }


def test_dashboard_excludes_test_cases_but_keeps_them_visible_and_can_include_them(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "test-data-owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(factory, business_id="biz-test-data", case_id="test-case", lead_id="test-lead")
    with factory() as unit_of_work:
        case = unit_of_work.cases.get("biz-test-data", "test-case")
        assert case is not None
        # is_test is immutable after creation in normal operation; this test
        # deliberately seeds a historic trial case through the repository.
        unit_of_work.session.execute(
            update(ProcessCaseRow).where(ProcessCaseRow.id == "test-case").values(is_test=True)
        )
        live_lead = Lead("live-lead", name="Grace")
        live_case = ProcessCase("live-case", "biz-test-data", live_lead, ProcessState.BOOKED, NOW + timedelta(days=1), NOW + timedelta(days=1))
        live_case.record(ProcessEvent("BOOKING_CREATED", occurred_at=NOW + timedelta(days=1)))
        unit_of_work.leads.add("biz-test-data", live_lead, live_case.created_at)
        unit_of_work.cases.add(live_case)
        unit_of_work.events.add_many("biz-test-data", "live-case", live_case.event_history)
        unit_of_work.commit()
    link_business(factory, business_id="biz-test-data", user_id=me["user_id"])

    default_metrics = client.get("/api/v1/businesses/biz-test-data/analytics", headers={"Authorization": f"Bearer {token}"})
    assert default_metrics.status_code == 200
    assert default_metrics.json()["total_cases"] == 1
    assert default_metrics.json()["hidden_test_cases"] == 1
    assert default_metrics.json()["hidden_test_conversations"] == 1
    assert default_metrics.json()["booked_cases"] == 1
    cases = client.get("/api/v1/businesses/biz-test-data/cases", headers={"Authorization": f"Bearer {token}"}).json()["cases"]
    assert {case["case_id"] for case in cases} == {"live-case"}

    including_test = client.get(
        "/api/v1/businesses/biz-test-data/analytics?include_test=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert including_test.status_code == 200
    assert including_test.json()["total_cases"] == 2
    assert including_test.json()["includes_test_data"] is True
    included_cases = client.get(
        "/api/v1/businesses/biz-test-data/cases?include_test=true",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["cases"]
    assert {case["case_id"] for case in included_cases} == {"test-case", "live-case"}
    assert next(case for case in included_cases if case["case_id"] == "test-case")["is_test"] is True


def test_dashboard_statistics_baseline_filters_metrics_and_can_be_cleared(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "baseline-owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(factory, business_id="biz-baseline", case_id="old-case", lead_id="old-lead")
    link_business(factory, business_id="biz-baseline", user_id=me["user_id"])
    with factory() as unit_of_work:
        live_lead = Lead("new-lead", name="Grace")
        live_case = ProcessCase("new-case", "biz-baseline", live_lead, ProcessState.BOOKED, NOW + timedelta(days=2), NOW + timedelta(days=2))
        live_case.record(ProcessEvent("BOOKING_CREATED", occurred_at=NOW + timedelta(days=2)))
        unit_of_work.leads.add("biz-baseline", live_lead, live_case.created_at)
        unit_of_work.cases.add(live_case)
        unit_of_work.events.add_many("biz-baseline", live_case.case_id, live_case.event_history)
        unit_of_work.businesses.update_reporting_settings("biz-baseline", stats_since=NOW + timedelta(days=1))
        unit_of_work.commit()

    filtered = client.get("/api/v1/businesses/biz-baseline/analytics", headers={"Authorization": f"Bearer {token}"})
    assert filtered.status_code == 200
    assert filtered.json()["total_cases"] == 1
    assert filtered.json()["booked_cases"] == 1
    filtered_cases = client.get(
        "/api/v1/businesses/biz-baseline/cases",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert {case["case_id"] for case in filtered_cases.json()["cases"]} == {"new-case"}
    queue = client.get(
        "/api/v1/businesses/biz-baseline/cases?ignore_baseline=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert {case["case_id"] for case in queue.json()["cases"]} == {"old-case", "new-case"}
    cleared = client.patch(
        "/api/v1/businesses/biz-baseline/analytics/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"clear_statistics_baseline": True},
    )
    assert cleared.status_code == 200 and cleared.json()["stats_since"] is None
    restored = client.get("/api/v1/businesses/biz-baseline/analytics", headers={"Authorization": f"Bearer {token}"})
    assert restored.status_code == 200
    assert restored.json()["total_cases"] == 2
    live_date = (NOW + timedelta(days=2)).date().isoformat()
    date_filtered_cases = client.get(
        f"/api/v1/businesses/biz-baseline/cases?start_date={live_date}&end_date={live_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert {case["case_id"] for case in date_filtered_cases.json()["cases"]} == {"new-case"}


def test_dashboard_with_only_test_cases_has_zero_rates(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "zero-owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(factory, business_id="biz-zero", case_id="only-test", lead_id="only-test-lead")
    with factory() as unit_of_work:
        unit_of_work.session.execute(update(ProcessCaseRow).where(ProcessCaseRow.id == "only-test").values(is_test=True))
        unit_of_work.commit()
    link_business(factory, business_id="biz-zero", user_id=me["user_id"])
    metrics = client.get("/api/v1/businesses/biz-zero/analytics", headers={"Authorization": f"Bearer {token}"})
    assert metrics.status_code == 200
    assert metrics.json()["total_cases"] == 0
    assert metrics.json()["booking_conversion_rate"] == 0.0
    assert metrics.json()["escalation_rate"] == 0.0
    assert metrics.json()["lost_rate"] == 0.0


def test_dashboard_analytics_is_not_truncated_to_the_case_list_page_size(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "all-cases-owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    with factory() as unit_of_work:
        unit_of_work.businesses.add(
            Business("biz-all-cases", "All cases", NOW, NOW, plan="starter", subscription_status="active")
        )
        leads = [Lead(f"lead-{index}", name=f"Lead {index}") for index in range(201)]
        for lead in leads:
            unit_of_work.leads.add("biz-all-cases", lead, NOW)
        unit_of_work.session.flush()
        for index, lead in enumerate(leads):
            unit_of_work.cases.add(
                ProcessCase(f"case-{index}", "biz-all-cases", lead, created_at=NOW, updated_at=NOW)
            )
        unit_of_work.commit()
    link_business(factory, business_id="biz-all-cases", user_id=me["user_id"])

    metrics = client.get("/api/v1/businesses/biz-all-cases/analytics", headers={"Authorization": f"Bearer {token}"})
    assert metrics.status_code == 200
    assert metrics.json()["total_cases"] == 201


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
    assert case["lifecycle_actions"] == []


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


def test_staff_can_record_payment_on_a_won_case(dashboard_environment) -> None:
    client, factory = dashboard_environment
    token = signup_and_login(client, "lifecycle-owner@example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    seed_case_with_conversation(factory, business_id="biz-lifecycle", case_id="case-won", lead_id="lead-won")
    link_business(factory, business_id="biz-lifecycle", user_id=me["user_id"])
    with factory() as unit_of_work:
        unit_of_work.session.execute(
            update(ProcessCaseRow)
            .where(ProcessCaseRow.id == "case-won")
            .values(current_state="WON", version=ProcessCaseRow.version + 1)
        )
        unit_of_work.commit()

    blocked = client.post(
        "/api/v1/businesses/biz-lifecycle/cases/case-won/lifecycle",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "request_review"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "invalid_lifecycle_action"

    paid = client.post(
        "/api/v1/businesses/biz-lifecycle/cases/case-won/lifecycle",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "record_payment"},
    )
    assert paid.status_code == 200
    body = paid.json()
    assert body["case"]["current_state"] == "PAID"
    assert body["case"]["lifecycle_actions"] == ["mark_completed"]
    assert body["conversation"]["case_state"] == "PAID"
