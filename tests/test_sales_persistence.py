from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from src.domain.models import Lead, ProcessCase
from src.domain.sales import (
    CommitmentLevel,
    CustomerEvidence,
    CustomerSalesProfile,
    SalesKnowledgeCard,
    SalesKnowledgeStatus,
    SalesMove,
    SalesObjection,
    SalesObjectionRecord,
    ObjectionStatus,
    ObjectionType,
    SalesPlaybookStatus,
    SalesPlaybookVersion,
    SalesStage,
    SalesTurn,
)
from src.domain.tenancy import Business
from src.persistence.errors import StaleSalesObjectionError, StaleSalesProfileError
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def uow_factory(tmp_path: Path):
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'sales.db'}")
    Base.metadata.create_all(engine)
    yield SQLAlchemyUnitOfWork.factory_for_engine(engine)
    engine.dispose()


def _seed_case(uow_factory, business_id: str, case_id: str) -> None:
    lead = Lead(f"lead-{business_id}", "Ada")
    case = ProcessCase(case_id, business_id, lead, created_at=NOW, updated_at=NOW)
    with uow_factory() as uow:
        uow.businesses.add(Business(business_id, f"Business {business_id}", NOW, NOW))
        uow.leads.add(business_id, lead, NOW)
        uow.cases.add(case)
        uow.commit()


def test_sales_profile_round_trip_is_tenant_scoped(uow_factory) -> None:
    _seed_case(uow_factory, "biz-1", "case-1")
    _seed_case(uow_factory, "biz-2", "case-2")
    profile = CustomerSalesProfile(
        business_id="biz-1",
        case_id="case-1",
        stage=SalesStage.DISCOVERY,
        customer_goal="book more qualified calls",
        current_problem="missed inbound leads",
        decision_criteria=("reliability", "price"),
        commitment_level=CommitmentLevel.INTERESTED,
    )
    with uow_factory() as uow:
        uow.sales_profiles.add(profile, now=NOW)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.sales_profiles.get("biz-1", "case-1")
        cross_tenant = uow.sales_profiles.get("biz-2", "case-1")
    assert stored == profile
    assert cross_tenant is None


def test_sales_profile_save_uses_optimistic_version(uow_factory) -> None:
    _seed_case(uow_factory, "biz-1", "case-1")
    profile = CustomerSalesProfile("biz-1", "case-1")
    with uow_factory() as uow:
        uow.sales_profiles.add(profile, now=NOW)
        uow.commit()
    with uow_factory() as uow:
        loaded = uow.sales_profiles.get("biz-1", "case-1")
        assert loaded is not None
        saved = uow.sales_profiles.save(
            replace(loaded, stage=SalesStage.DISCOVERY), loaded.version, now=NOW
        )
        assert saved.version == 1
        with pytest.raises(StaleSalesProfileError):
            uow.sales_profiles.save(loaded, loaded.version, now=NOW)


def test_sales_turn_is_append_only_and_idempotent_by_source_message(uow_factory) -> None:
    _seed_case(uow_factory, "biz-1", "case-1")
    turn = SalesTurn(
        turn_id="turn-1",
        business_id="biz-1",
        case_id="case-1",
        conversation_id=None,
        source_message_id="message-1",
        playbook_version=None,
        stage_before=SalesStage.GREETING,
        stage_after=SalesStage.DISCOVERY,
        move=SalesMove.GREET_AND_SET_CONTEXT,
        reason_code="conversation_started",
        knowledge_ids=(),
        business_fact_ids=(),
        customer_evidence=(CustomerEvidence("message-1", "Hi"),),
        analysis={"confidence": 0.99},
        validation={"passed": True},
        created_at=NOW,
    )
    with uow_factory() as uow:
        uow.sales_turns.add(turn)
        uow.commit()
    with uow_factory() as uow:
        assert uow.sales_turns.get_by_source_message("biz-1", "case-1", "message-1") == turn
        uow.sales_turns.add(replace(turn, turn_id="turn-2"))
        with pytest.raises(IntegrityError):
            uow.commit()


def test_only_approved_knowledge_is_listed_for_runtime(uow_factory) -> None:
    _seed_case(uow_factory, "biz-1", "case-1")
    approved = SalesKnowledgeCard(
        knowledge_id="price-1",
        business_id="biz-1",
        version=1,
        status=SalesKnowledgeStatus.APPROVED,
        source={"title": "Licensed method", "location": "chapter 2"},
        principle="Diagnose whether the concern is budget or value.",
        applicable_when=("price objection",),
        created_at=NOW,
    )
    candidate = replace(
        approved,
        knowledge_id="price-2",
        status=SalesKnowledgeStatus.CANDIDATE,
    )
    with uow_factory() as uow:
        uow.sales_knowledge.add(approved, now=NOW)
        uow.sales_knowledge.add(candidate, now=NOW)
        uow.commit()
    with uow_factory() as uow:
        assert uow.sales_knowledge.list_approved("biz-1") == (approved,)


def test_only_one_published_playbook_exists_per_business(uow_factory) -> None:
    _seed_case(uow_factory, "biz-1", "case-1")
    first = SalesPlaybookVersion(
        business_id="biz-1",
        version=1,
        status=SalesPlaybookStatus.PUBLISHED,
        configuration={"sales_goal": "book_consultation"},
        created_at=NOW,
        published_at=NOW,
    )
    second = replace(first, version=2)
    with uow_factory() as uow:
        uow.sales_playbooks.add(first)
        uow.commit()
    with uow_factory() as uow:
        assert uow.sales_playbooks.get_active("biz-1") == first
        uow.sales_playbooks.add(second)
        with pytest.raises(IntegrityError):
            uow.commit()


def test_objection_lifecycle_is_persisted_and_tenant_scoped(uow_factory) -> None:
    _seed_case(uow_factory, "biz-1", "case-1")
    _seed_case(uow_factory, "biz-2", "case-2")
    record = SalesObjectionRecord(
        objection_id="objection-1",
        business_id="biz-1",
        case_id="case-1",
        objection=SalesObjection(
            objection_type=ObjectionType.PRICE,
            status=ObjectionStatus.ACTIVE,
            evidence=CustomerEvidence("message-1", "That costs more than I expected"),
        ),
        created_at=NOW,
        updated_at=NOW,
    )
    with uow_factory() as uow:
        uow.sales_profiles.add(CustomerSalesProfile("biz-1", "case-1"), now=NOW)
        uow.commit()
    with uow_factory() as uow:
        uow.sales_objections.add(record)
        uow.commit()
    with uow_factory() as uow:
        assert uow.sales_objections.list_for_case("biz-1", "case-1") == (record,)
        assert uow.sales_objections.list_for_case("biz-2", "case-1") == ()
        addressed = replace(
            record,
            objection=replace(record.objection, status=ObjectionStatus.ADDRESSED, cause="value"),
        )
        addressed = uow.sales_objections.save(addressed, expected_version=0)
        uow.commit()
    with uow_factory() as uow:
        stored = uow.sales_objections.list_for_case("biz-1", "case-1")
    assert stored == (addressed,)

    with uow_factory() as uow:
        with pytest.raises(StaleSalesObjectionError):
            uow.sales_objections.save(record, expected_version=0)
