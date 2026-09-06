"""Staff Sales API contracts, review transitions, and tenant isolation."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import Settings
from src.domain.models import Lead, ProcessCase
from src.domain.sales import (
    CustomerEvidence,
    CustomerSalesProfile,
    SalesKnowledgeCard,
    SalesKnowledgeStatus,
    SalesMove,
    SalesPlaybookStatus,
    SalesPlaybookVersion,
    SalesStage,
    SalesTurn,
)
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


NOW = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def sales_api_environment(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'sales-api.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    app = create_app(settings=Settings(database_url=database_url, app_env="test"))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, factory
    engine.dispose()


def _signup(client: TestClient, email: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return response.json()["token"], response.json()["user"]["user_id"]


def _seed(factory, *, business_id: str, user_id: str) -> None:
    with factory() as uow:
        uow.businesses.add(Business(business_id, business_id, NOW, NOW))
        uow.session.flush()
        user = uow.staff_users.get(user_id)
        uow.staff_users.save(user.with_business(business_id))
        uow.leads.add(business_id, Lead(f"lead-{business_id}", name="Ada"), NOW)
        case = ProcessCase(
            f"case-{business_id}", business_id, uow.leads.get(business_id, f"lead-{business_id}"),
            ProcessState.QUALIFYING, NOW, NOW,
        )
        uow.cases.add(case)
        uow.session.flush()
        uow.sales_profiles.add(
            CustomerSalesProfile(
                business_id,
                case.case_id,
                stage=SalesStage.DISCOVERY,
                customer_goal="Improve follow-up",
                current_problem="Leads wait too long",
                desired_outcome="Reply immediately",
            ),
            now=NOW,
        )
        uow.sales_playbooks.add(
            SalesPlaybookVersion(
                business_id, 1, SalesPlaybookStatus.PUBLISHED,
                {"method": "consultative"}, NOW, NOW,
            )
        )
        uow.sales_knowledge.add(
            SalesKnowledgeCard(
                "discovery-1", business_id, 1, SalesKnowledgeStatus.CANDIDATE,
                {"title": "Owner source", "location": "section 1"},
                "Ask one relevant question.", ("stage == DISCOVERY",), created_at=NOW,
            ),
            now=NOW,
        )
        uow.sales_turns.add(
            SalesTurn(
                f"turn-{business_id}", business_id, case.case_id, None, f"message-{business_id}", 1,
                SalesStage.GREETING, SalesStage.DISCOVERY,
                SalesMove.GREET_AND_SET_CONTEXT, "conversation_started",
                (), (), (CustomerEvidence(f"message-{business_id}", "Hello"),), {}, {}, NOW,
            )
        )
        uow.commit()


def test_sales_configuration_and_case_contracts(sales_api_environment) -> None:
    client, factory = sales_api_environment
    token, user_id = _signup(client, "sales-owner@example.com")
    _seed(factory, business_id="biz-1", user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}

    playbook = client.get("/api/v1/businesses/biz-1/sales/playbook", headers=headers)
    assert playbook.status_code == 200
    assert playbook.json()["version"] == 1
    assert playbook.json()["status"] == "PUBLISHED"

    cards = client.get("/api/v1/businesses/biz-1/sales/knowledge-cards", headers=headers)
    assert cards.status_code == 200
    assert cards.json()["cards"][0]["status"] == "CANDIDATE"

    context = client.get("/api/v1/businesses/biz-1/sales/cases/case-biz-1", headers=headers)
    assert context.status_code == 200
    assert context.json()["stage"] == "DISCOVERY"
    assert context.json()["next_approved_action"] == "CONFIRM_CUSTOMER_NEED"

    turns = client.get("/api/v1/businesses/biz-1/sales/cases/case-biz-1/turns", headers=headers)
    assert turns.status_code == 200
    assert turns.json()["turns"][0]["knowledge_ids"] == []
    assert turns.json()["turns"][0]["customer_evidence"][0]["source_message_id"] == "message-biz-1"


def test_candidate_can_be_reviewed_only_once(sales_api_environment) -> None:
    client, factory = sales_api_environment
    token, user_id = _signup(client, "reviewer@example.com")
    _seed(factory, business_id="biz-1", user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}
    path = "/api/v1/businesses/biz-1/sales/knowledge-cards/discovery-1/versions/1/approve"

    approved = client.post(path, headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["reviewed_by"] == user_id
    assert approved.json()["reviewed_at"] is not None
    conflict = client.post(path, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "sales_knowledge_already_reviewed"


def test_sales_api_requires_auth_and_prevents_cross_tenant_access(sales_api_environment) -> None:
    client, factory = sales_api_environment
    owner_token, owner_id = _signup(client, "owner-one@example.com")
    other_token, other_id = _signup(client, "owner-two@example.com")
    _seed(factory, business_id="biz-1", user_id=owner_id)
    _seed(factory, business_id="biz-2", user_id=other_id)

    path = "/api/v1/businesses/biz-1/sales/knowledge-cards"
    assert client.get(path).status_code == 401
    forbidden = client.get(path, headers={"Authorization": f"Bearer {other_token}"})
    assert forbidden.status_code == 403
    allowed = client.get(path, headers={"Authorization": f"Bearer {owner_token}"})
    assert allowed.status_code == 200
    assert {card["business_id"] for card in allowed.json()["cards"]} == {"biz-1"}


def test_knowledge_status_filter_and_missing_resources(sales_api_environment) -> None:
    client, factory = sales_api_environment
    token, user_id = _signup(client, "filter-owner@example.com")
    _seed(factory, business_id="biz-1", user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}

    empty = client.get(
        "/api/v1/businesses/biz-1/sales/knowledge-cards?status=APPROVED",
        headers=headers,
    )
    assert empty.status_code == 200
    assert empty.json() == {"cards": []}
    missing = client.get(
        "/api/v1/businesses/biz-1/sales/cases/unknown", headers=headers
    )
    assert missing.status_code == 404
