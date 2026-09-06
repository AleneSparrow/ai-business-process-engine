from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.ai.models import AIInvocationMetadata
from src.ai.sales_response_generator import GeneratedSalesResponse
from src.ai.sales_response_models import SalesResponseOutput
from src.ai.sales_turn_analyzer import AnalyzedSalesTurn
from src.domain.conversations import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageDirection,
    MessageRole,
)
from src.domain.models import Lead, ProcessCase
from src.domain.sales import (
    CustomerEvidence,
    ObjectionStatus,
    ObjectionType,
    SalesMove,
    SalesObjection,
    SalesPlaybookStatus,
    SalesPlaybookVersion,
    SalesShadowJob,
    SalesShadowJobStatus,
    SalesShadowStatus,
    SalesStage,
    SalesTurnAnalysis,
)
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.sales_shadow_orchestrator import SalesShadowOrchestrator
from src.persistence.sales_shadow_service import SalesShadowService
from src.persistence.sales_shadow_worker import SalesShadowWorker
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
LIVE_REPLY = "Thanks for reaching out. A team member can help with the next step."
SHADOW_REPLY = "What outcome matters most for you right now?"


def _metadata() -> AIInvocationMetadata:
    return AIInvocationMetadata(
        "fake", "test-model", "sales-test", "v1", "sales_test", 1, True, "ok",
    )


class FixedAnalyzer:
    def analyze(self, **kwargs):
        return AnalyzedSalesTurn(
            SalesTurnAnalysis(observed_stage=SalesStage.GREETING, confidence=0.9),
            _metadata(),
        )


class ObjectionAnalyzer:
    def analyze(self, **kwargs):
        return AnalyzedSalesTurn(
            SalesTurnAnalysis(
                observed_stage=SalesStage.OBJECTION_HANDLING,
                confidence=0.92,
                objections=(SalesObjection(
                    ObjectionType.PRICE, ObjectionStatus.ACTIVE,
                    CustomerEvidence("msg-in", "That is more than I expected"),
                ),),
            ),
            _metadata(),
        )


class EchoGenerator:
    def generate(self, value):
        return GeneratedSalesResponse(
            SalesResponseOutput(move=value.approved_move, message_text=SHADOW_REPLY),
            _metadata(),
        )


@pytest.fixture
def uow_factory(tmp_path: Path):
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'shadow-worker.db'}")
    Base.metadata.create_all(engine)
    yield SQLAlchemyUnitOfWork.factory_for_engine(engine)
    engine.dispose()


def _seed_reply_and_job(uow_factory, *, business_id="biz-1", customer_text="I need faster follow-up"):
    lead = Lead(f"lead-{business_id}", "Ada")
    case = ProcessCase(
        f"case-{business_id}", business_id, lead, ProcessState.QUALIFYING, NOW, NOW,
    )
    with uow_factory() as uow:
        uow.businesses.add(Business(business_id, business_id, NOW, NOW))
        uow.leads.add(business_id, lead, NOW)
        uow.cases.add(case)
        uow.session.flush()
        uow.conversations.add(Conversation(
            f"conversation-{business_id}", business_id, "0" * 64, "web",
            ConversationStatus.AI_ACTIVE, NOW, NOW, NOW, NOW + timedelta(days=1),
            lead_id=lead.lead_id, case_id=case.case_id,
        ))
        uow.session.flush()
        uow.conversation_messages.add(ConversationMessage(
            "msg-in", business_id, f"conversation-{business_id}", 1,
            MessageDirection.INBOUND, MessageRole.CUSTOMER, customer_text, NOW,
        ))
        uow.conversation_messages.add(ConversationMessage(
            "msg-out", business_id, f"conversation-{business_id}", 2,
            MessageDirection.OUTBOUND, MessageRole.ASSISTANT, LIVE_REPLY, NOW,
        ))
        uow.session.flush()
        uow.sales_playbooks.add(SalesPlaybookVersion(
            business_id, 1, SalesPlaybookStatus.PUBLISHED, {"method": "consultative"}, NOW, NOW,
        ))
        uow.sales_shadow_jobs.add(SalesShadowJob(
            f"job-{business_id}", business_id, case.case_id, f"conversation-{business_id}",
            "msg-in", "msg-out", SalesShadowJobStatus.PENDING, 0, 3, NOW, NOW, NOW,
        ))
        uow.commit()
    return case.case_id


def _worker(uow_factory) -> SalesShadowWorker:
    service = SalesShadowService(uow_factory)
    return SalesShadowWorker(
        uow_factory, FixedAnalyzer(), SalesShadowOrchestrator(EchoGenerator(), service),
        worker_id="worker-1",
    )


def test_shadow_worker_does_not_change_process_state_or_customer_messages(uow_factory) -> None:
    case_id = _seed_reply_and_job(uow_factory)
    assert _worker(uow_factory).run_one(now=NOW) is True

    with uow_factory() as uow:
        case = uow.cases.get("biz-1", case_id)
        messages = sorted(
            uow.conversation_messages.list_for_conversation("biz-1", "conversation-biz-1"),
            key=lambda item: item.sequence_number,
        )
        job = uow.sales_shadow_jobs.get("biz-1", "job-biz-1")
        results = uow.sales_shadow_results.list_for_case("biz-1", case_id)
        other = uow.sales_shadow_results.list_for_case("other", case_id)

    assert case is not None
    assert case.current_state is ProcessState.QUALIFYING
    assert [(item.direction, item.text) for item in messages] == [
        (MessageDirection.INBOUND, "I need faster follow-up"),
        (MessageDirection.OUTBOUND, LIVE_REPLY),
    ]
    assert job is not None
    assert job.status is SalesShadowJobStatus.COMPLETED
    assert len(results) == 1
    assert results[0].proposed_response_text == SHADOW_REPLY
    assert results[0].delivered_response_text == LIVE_REPLY
    assert results[0].status is SalesShadowStatus.VALID
    assert other == ()


def test_stop_message_records_shadow_error_without_sending_or_changing_state(uow_factory) -> None:
    case_id = _seed_reply_and_job(uow_factory, customer_text="STOP")
    assert _worker(uow_factory).run_one(now=NOW) is True

    with uow_factory() as uow:
        case = uow.cases.get("biz-1", case_id)
        messages = sorted(
            uow.conversation_messages.list_for_conversation("biz-1", "conversation-biz-1"),
            key=lambda item: item.sequence_number,
        )
        results = uow.sales_shadow_results.list_for_case("biz-1", case_id)

    assert case is not None
    assert case.current_state is ProcessState.QUALIFYING
    assert [item.text for item in messages] == ["STOP", LIVE_REPLY]
    assert results[0].status is SalesShadowStatus.VALIDATOR_ERROR
    assert results[0].proposed_response_text is None
    assert results[0].delivered_response_text == LIVE_REPLY
    assert "contact_not_allowed" in results[0].violations


def test_shadow_worker_persists_objections_and_turns_without_changing_process_state(uow_factory) -> None:
    case_id = _seed_reply_and_job(uow_factory, customer_text="That is more than I expected")
    service = SalesShadowService(uow_factory)
    worker = SalesShadowWorker(
        uow_factory, ObjectionAnalyzer(), SalesShadowOrchestrator(EchoGenerator(), service),
        worker_id="worker-1",
    )
    assert worker.run_one(now=NOW) is True

    with uow_factory() as uow:
        case = uow.cases.get("biz-1", case_id)
        objections = uow.sales_objections.list_for_case("biz-1", case_id)
        turns = uow.sales_turns.list_for_case("biz-1", case_id)
        profile = uow.sales_profiles.get("biz-1", case_id)

    assert case is not None
    assert case.current_state is ProcessState.QUALIFYING
    assert len(objections) == 1
    assert objections[0].objection.objection_type is ObjectionType.PRICE
    assert objections[0].objection.evidence.excerpt == "That is more than I expected"
    assert turns[0].move is SalesMove.DIAGNOSE_OBJECTION
    assert profile is not None
    assert profile.stage is SalesStage.OBJECTION_HANDLING
    assert profile.last_move is SalesMove.DIAGNOSE_OBJECTION
