"""Staff Sales API contracts, review transitions, and tenant isolation."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import Settings
from src.domain.conversations import Conversation, ConversationStatus
from src.domain.models import Lead, ProcessCase
from src.domain.sales import (
    CustomerEvidence,
    CustomerSalesProfile,
    SalesKnowledgeCard,
    SalesKnowledgeStatus,
    SalesMove,
    SalesPlaybookStatus,
    SalesPlaybookVersion,
    SalesShadowResult,
    SalesShadowStatus,
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


def _import_payload(knowledge_id: str = "imported-1", version: int = 1) -> dict:
    return {
        "cards": [{
            "knowledge_id": knowledge_id,
            "version": version,
            "source": {"title": "Verified source", "location": "chapter 2"},
            "principle": "Ask one grounded question.",
            "applicable_when": ["stage == DISCOVERY"],
            "prohibited_when": ["customer already answered"],
            "required_sequence": [],
            "forbidden_actions": ["invent facts"],
            "approved_examples": ["What outcome matters most?"],
        }]
    }


def test_knowledge_import_dry_run_then_candidate_only_import(sales_api_environment) -> None:
    client, factory = sales_api_environment
    token, user_id = _signup(client, "import-owner@example.com")
    _seed(factory, business_id="biz-1", user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}
    validate_path = "/api/v1/businesses/biz-1/sales/knowledge-cards/import/validate"
    import_path = "/api/v1/businesses/biz-1/sales/knowledge-cards/import"

    dry_run = client.post(validate_path, headers=headers, json=_import_payload())
    assert dry_run.status_code == 200
    assert dry_run.json() == {
        "valid": True,
        "imported": False,
        "cards_are_candidates": True,
        "checks": [{"knowledge_id": "imported-1", "version": 1, "status": "READY"}],
    }
    with factory() as uow:
        assert uow.sales_knowledge.get("biz-1", "imported-1", 1) is None

    imported = client.post(import_path, headers=headers, json=_import_payload())
    assert imported.status_code == 200
    assert imported.json()["imported"] is True
    with factory() as uow:
        card = uow.sales_knowledge.get("biz-1", "imported-1", 1)
    assert card is not None
    assert card.status is SalesKnowledgeStatus.CANDIDATE

    conflict = client.post(import_path, headers=headers, json=_import_payload())
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "sales_knowledge_version_conflict"


def test_knowledge_import_rejects_status_and_duplicate_payload_versions(sales_api_environment) -> None:
    client, factory = sales_api_environment
    token, user_id = _signup(client, "strict-import@example.com")
    _seed(factory, business_id="biz-1", user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}
    path = "/api/v1/businesses/biz-1/sales/knowledge-cards/import/validate"
    payload = _import_payload()
    payload["cards"][0]["status"] = "APPROVED"
    assert client.post(path, headers=headers, json=payload).status_code == 422

    duplicate = _import_payload()
    duplicate["cards"].append(dict(duplicate["cards"][0]))
    assert client.post(path, headers=headers, json=duplicate).status_code == 422


def _seed_shadow_result(factory, *, business_id: str) -> None:
    with factory() as uow:
        uow.conversations.add(Conversation(
            f"conversation-{business_id}", business_id, "0" * 64, "web",
            ConversationStatus.AI_ACTIVE, NOW, NOW, NOW, NOW + timedelta(days=1),
            lead_id=f"lead-{business_id}", case_id=f"case-{business_id}",
        ))
        uow.sales_shadow_results.add(SalesShadowResult(
            f"shadow-{business_id}", business_id, f"case-{business_id}",
            f"conversation-{business_id}", f"message-{business_id}",
            SalesMove.ASK_DISCOVERY_QUESTION, SalesShadowStatus.VALID,
            "What outcome matters most right now?",
            "Thanks — a team member can help with the next step.",
            (), (), (), (), "2026-09-06.v2", "test-model", NOW,
        ))
        uow.commit()


def test_shadow_results_are_listed_evaluated_once_and_tenant_scoped(sales_api_environment) -> None:
    client, factory = sales_api_environment
    owner_token, owner_id = _signup(client, "shadow-owner@example.com")
    other_token, other_id = _signup(client, "shadow-other@example.com")
    _seed(factory, business_id="biz-1", user_id=owner_id)
    _seed(factory, business_id="biz-2", user_id=other_id)
    _seed_shadow_result(factory, business_id="biz-1")
    owner = {"Authorization": f"Bearer {owner_token}"}
    other = {"Authorization": f"Bearer {other_token}"}
    list_path = "/api/v1/businesses/biz-1/sales/cases/case-biz-1/shadow-results"
    evaluate_path = f"{list_path}/shadow-biz-1/evaluate"

    listed = client.get(list_path, headers=owner)
    assert listed.status_code == 200
    result = listed.json()["results"][0]
    assert result["shadow_id"] == "shadow-biz-1"
    assert result["conversation_id"] == "conversation-biz-1"
    assert result["status"] == "VALID"
    assert result["approved_move"] == "ASK_DISCOVERY_QUESTION"
    assert result["proposed_response_text"] == "What outcome matters most right now?"
    assert result["delivered_response_text"] == "Thanks — a team member can help with the next step."
    assert result["evaluation"] is None
    assert client.get(list_path, headers=other).status_code == 403

    evaluated = client.post(evaluate_path, headers=owner, json={"evaluation": "APPROVED"})
    assert evaluated.status_code == 200
    body = evaluated.json()
    assert body["status"] == "EVALUATED"
    assert body["evaluation"] == "APPROVED"
    assert body["evaluated_by"] == owner_id
    assert body["evaluated_at"] is not None

    conflict = client.post(evaluate_path, headers=owner, json={"evaluation": "WRONG_TONE"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "sales_shadow_already_evaluated"

    missing = client.post(
        f"{list_path}/unknown/evaluate", headers=owner, json={"evaluation": "UNSAFE"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "sales_shadow_not_found"
    assert client.post(
        "/api/v1/businesses/biz-1/sales/cases/unknown/shadow-results/shadow-biz-1/evaluate",
        headers=owner, json={"evaluation": "UNSAFE"},
    ).status_code == 404
    assert client.post(evaluate_path, headers=other, json={"evaluation": "UNSAFE"}).status_code == 403
    assert client.post(evaluate_path, json={"evaluation": "APPROVED"}).status_code == 401
