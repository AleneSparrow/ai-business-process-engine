import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.domain.events import EventType
from src.domain.models import DecisionType, Lead, ProcessCase, ProcessEvent, utc_now
from src.domain.qualification import IncomingMessage, IntentResult
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.engine.decision_router import DecisionRequest
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.engine.process_engine import ProcessEngine
from src.engine.question_generator import DeterministicQuestionGenerator
from src.persistence.errors import IdempotencyCollisionError, StaleCaseError
from src.persistence.lead_intake import PersistentLeadIntakeService
from src.persistence.sqlalchemy_models import (
    Base,
    LeadRow,
    ProcessCaseRow,
    ProcessedMessageRow,
    ProcessEventRow,
)
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 11, 8, 0, tzinfo=timezone.utc)


def dna() -> dict:
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        return json.load(file)


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'persistence.db'}"


@pytest.fixture
def uow_factory(database_url: str):
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    yield factory
    engine.dispose()


def seed_business(factory, business_id: str = "acme-home-services", *, with_dna: bool = True) -> None:
    now = utc_now()
    with factory() as uow:
        uow.businesses.add(Business(business_id, business_id, now, now))
        if with_dna:
            configuration = dna()
            configuration["business"]["id"] = business_id
            uow.business_dna.add_version(business_id, configuration)
        uow.commit()


def test_persistence_survives_repository_and_engine_reinstantiation(database_url: str) -> None:
    first_engine = create_database_engine(database_url)
    Base.metadata.create_all(first_engine)
    first_factory = SQLAlchemyUnitOfWork.factory_for_engine(first_engine)
    seed_business(first_factory)
    lead = Lead("lead-restart", "Ada", "ada@example.com", "+13125550100")
    case = ProcessCase("case-restart", "acme-home-services", lead)
    with first_factory() as uow:
        uow.leads.add(case.business_id, lead, case.created_at)
        uow.cases.add(case)
        uow.events.add(case.business_id, case.case_id, ProcessEvent("CREATED"))
        uow.commit()
    first_engine.dispose()

    second_engine = create_database_engine(database_url)
    second_factory = SQLAlchemyUnitOfWork.factory_for_engine(second_engine)
    with second_factory() as uow:
        restored = uow.cases.get("acme-home-services", "case-restart")
        assert restored is not None
        assert restored.lead.email == "ada@example.com"
        assert [event.event_type for event in restored.event_history] == ["CREATED"]
    second_engine.dispose()


def test_repository_queries_enforce_tenant_isolation(uow_factory) -> None:
    seed_business(uow_factory, "tenant-a")
    seed_business(uow_factory, "tenant-b")
    lead = Lead("tenant-a-lead", "Ada")
    case = ProcessCase("tenant-a-case", "tenant-a", lead)
    event = ProcessEvent("TENANT_A_EVENT")
    with uow_factory() as uow:
        uow.leads.add("tenant-a", lead, case.created_at)
        uow.cases.add(case)
        uow.events.add("tenant-a", case.case_id, event)
        uow.commit()

    with uow_factory() as uow:
        assert uow.leads.get("tenant-b", lead.lead_id) is None
        assert uow.cases.get("tenant-b", case.case_id) is None
        assert uow.events.list_for_case("tenant-b", case.case_id) == ()
        assert uow.leads.get("tenant-a", lead.lead_id) is not None
        assert uow.cases.get("tenant-a", case.case_id) is not None
        assert len(uow.events.list_for_case("tenant-a", case.case_id)) == 1


def test_business_dna_versions_preserve_history_and_one_active_version(uow_factory) -> None:
    seed_business(uow_factory, with_dna=False)
    first = dna()
    second = dna()
    second["business"]["description"] = "Version two"
    with uow_factory() as uow:
        version_one = uow.business_dna.add_version("acme-home-services", first)
        version_two = uow.business_dna.add_version("acme-home-services", second)
        uow.commit()
        assert (version_one.version, version_two.version) == (1, 2)

    with uow_factory() as uow:
        active = uow.business_dna.get_active("acme-home-services")
        versions = uow.business_dna.list_versions("acme-home-services")
        assert active is not None and active.version == 2
        assert [version.active for version in versions] == [False, True]
        assert versions[0].configuration["business"]["description"] != "Version two"


def test_rollback_leaves_no_partial_lead_case_or_event(uow_factory) -> None:
    seed_business(uow_factory)
    lead = Lead("rollback-lead", "Ada")
    case = ProcessCase("rollback-case", "acme-home-services", lead)
    with pytest.raises(RuntimeError):
        with uow_factory() as uow:
            uow.leads.add(case.business_id, lead, case.created_at)
            uow.cases.add(case)
            uow.events.add(case.business_id, case.case_id, ProcessEvent("SHOULD_ROLL_BACK"))
            raise RuntimeError("force rollback")

    with uow_factory() as uow:
        assert uow.leads.get(case.business_id, lead.lead_id) is None
        assert uow.cases.get(case.business_id, case.case_id) is None
        assert uow.events.list_for_case(case.business_id, case.case_id) == ()


def test_optimistic_conflict_rolls_back_losing_state_and_events(uow_factory) -> None:
    seed_business(uow_factory)
    lead = Lead("conflict-lead", "Ada")
    original = ProcessCase("conflict-case", "acme-home-services", lead)
    with uow_factory() as uow:
        uow.leads.add(original.business_id, lead, original.created_at)
        uow.cases.add(original)
        uow.commit()

    first = uow_factory()
    second = uow_factory()
    first.__enter__()
    second.__enter__()
    try:
        first_case = first.cases.get("acme-home-services", original.case_id)
        second_case = second.cases.get("acme-home-services", original.case_id)
        assert first_case is not None and second_case is not None
        ProcessEngine().receive(
            first_case,
            ProcessEvent("FIRST", event_id="first-transition"),
            DecisionRequest(DecisionType.RULE, ProcessState.CONTACTED),
        )
        first.cases.save(first_case, expected_version=0)
        first.events.add_many(first_case.business_id, first_case.case_id, first_case.event_history)
        first.commit()

        ProcessEngine().receive(
            second_case,
            ProcessEvent("SECOND", event_id="second-transition"),
            DecisionRequest(DecisionType.RULE, ProcessState.LOST),
        )
        with pytest.raises(StaleCaseError):
            second.cases.save(second_case, expected_version=0)
        second.rollback()
    finally:
        first.__exit__(None, None, None)
        second.__exit__(None, None, None)

    with uow_factory() as uow:
        persisted = uow.cases.get("acme-home-services", original.case_id)
        assert persisted is not None
        assert persisted.current_state is ProcessState.CONTACTED
        assert persisted.version == 1
        assert "second-transition" not in {event.event_id for event in persisted.event_history}
        assert "first-transition" in {event.event_id for event in persisted.event_history}


def test_rehydrated_case_rejects_duplicate_event_id_and_keeps_one_effect(uow_factory) -> None:
    """Regression test for the rehydration idempotency gap: a ProcessCase
    reloaded fresh from SQLite (a brand-new process, e.g. after a restart
    or a retried webhook -- not the same in-memory instance that originally
    processed the event) must recognize a previously-processed event_id as
    a duplicate and refuse to reapply its business effect (the state
    change), exactly as it would for a same-process replay."""
    seed_business(uow_factory)
    lead = Lead("rehydrate-lead", "Ada")
    case = ProcessCase("rehydrate-case", "acme-home-services", lead)
    with uow_factory() as uow:
        uow.leads.add(case.business_id, lead, case.created_at)
        uow.cases.add(case)
        uow.commit()

    with uow_factory() as uow:
        loaded = uow.cases.get(case.business_id, case.case_id)
        assert loaded is not None
        ProcessEngine().receive(
            loaded,
            ProcessEvent("first_contact", event_id="contact-event"),
            DecisionRequest(DecisionType.RULE, ProcessState.CONTACTED),
        )
        uow.cases.save(loaded, expected_version=0)
        uow.events.add_many(loaded.business_id, loaded.case_id, loaded.event_history)
        uow.commit()

    # A genuinely fresh load -- nothing here is the same Python object that
    # originally processed "contact-event"; only the persisted row and its
    # event_history are.
    with uow_factory() as uow:
        rehydrated = uow.cases.get(case.business_id, case.case_id)
        assert rehydrated is not None
        assert rehydrated.has_processed("contact-event")

        decision = ProcessEngine().receive(
            rehydrated,
            ProcessEvent("first_contact", event_id="contact-event"),
            DecisionRequest(DecisionType.RULE, ProcessState.QUALIFYING),
        )
        assert not decision.approved
        assert rehydrated.current_state is ProcessState.CONTACTED

        uow.cases.save(rehydrated, expected_version=rehydrated.version)
        uow.events.add_many(
            rehydrated.business_id, rehydrated.case_id, (rehydrated.event_history[-1],)
        )
        uow.commit()

    with uow_factory() as uow:
        final = uow.cases.get(case.business_id, case.case_id)
        assert final is not None
        assert final.current_state is ProcessState.CONTACTED  # never moved to QUALIFYING
        assert sum(event.event_type == EventType.STATE_CHANGED for event in final.event_history) == 1
        assert sum(event.event_type == EventType.DUPLICATE_IGNORED for event in final.event_history) == 1


def make_intake(factory, results: dict[str, IntentResult]) -> PersistentLeadIntakeService:
    return PersistentLeadIntakeService(
        factory,
        DeterministicIntentExtractor(results),
        DeterministicQuestionGenerator(),
    )


def intake_message(external_id: str, **changes: object) -> IncomingMessage:
    values: dict[str, object] = {
        "business_id": "acme-home-services",
        "channel": "sms",
        "external_message_id": external_id,
        "customer_name": "Ada",
        "phone": "+1 312 555 0100",
        "raw_text": "I need a diagnostic visit in 60601",
        "timestamp": NOW,
    }
    values.update(changes)
    return IncomingMessage(**values)  # type: ignore[arg-type]


def qualifying_intent() -> IntentResult:
    return IntentResult(
        service_requested="diagnostic-visit",
        customer_location="60601",
        confidence=0.95,
    )


def test_postgresql_compatible_intake_persists_and_is_idempotent(uow_factory) -> None:
    seed_business(uow_factory)
    intake = make_intake(uow_factory, {"persisted-message": qualifying_intent()})
    message = intake_message("persisted-message")

    first = intake.receive(message)
    duplicate = intake.receive(message)

    assert first.current_state is ProcessState.QUALIFIED
    assert duplicate.duplicate and duplicate.case_id == first.case_id
    with uow_factory() as uow:
        case = uow.cases.get(message.business_id, first.case_id)
        assert case is not None and case.current_state is ProcessState.QUALIFIED
        event_ids = [event.event_id for event in case.event_history]
        assert len(event_ids) == len(set(event_ids))
        assert sum(event.event_type == EventType.LEAD_INTAKE_RECEIVED for event in case.event_history) == 1
        qualification_event = next(
            event for event in case.event_history if event.event_type == EventType.QUALIFICATION_EVALUATED
        )
        assert qualification_event.payload["business_dna_version"] == 1


def test_intake_audit_proves_decisions_without_copying_customer_text_or_contact_pii(uow_factory) -> None:
    seed_business(uow_factory)
    raw_text = "My name is Ada Example; email ada.private@example.test and phone +1 312 555 0100"
    intake = make_intake(uow_factory, {
        "customer-message:ada.private@example.test": IntentResult(
            service_requested="diagnostic-visit",
            customer_location="60601",
            notes=raw_text,
            qualification_answers={"email": "ada.private@example.test"},
            confidence=0.95,
        ),
    })
    result = intake.receive(intake_message(
        "customer-message:ada.private@example.test",
        customer_name="Ada Example",
        email="ada.private@example.test",
        raw_text=raw_text,
    ))

    with uow_factory() as uow:
        events = uow.events.list_for_case("acme-home-services", result.case_id)
    # Domain payloads are immutable mapping proxies (and can contain nested
    # mapping proxies in decision metadata); their representation is enough
    # for this non-serialization privacy assertion.
    serialized = "\n".join(
        f"{event.event_id}\n{dict(event.payload)!r}" for event in events
    )
    for private_value in (raw_text, "Ada Example", "ada.private@example.test", "+1 312 555 0100"):
        assert private_value not in serialized
    intent_event = next(event for event in events if event.event_type == EventType.INTENT_EXTRACTED)
    assert intent_event.payload["location_provided"] is True
    assert intent_event.payload["answered_question_ids"] == ("email",)


def test_test_mode_classifies_only_new_cases_and_survives_rehydration(uow_factory) -> None:
    now = utc_now()
    with uow_factory() as uow:
        uow.businesses.add(Business("acme-home-services", "Acme", now, now, test_mode_enabled=True))
        configuration = dna()
        uow.business_dna.add_version("acme-home-services", configuration)
        uow.commit()

    intake = make_intake(uow_factory, {
        "test-mode": qualifying_intent(),
        "after-go-live": qualifying_intent(),
    })
    result = intake.receive(intake_message("test-mode"))
    with uow_factory() as uow:
        persisted = uow.cases.get("acme-home-services", result.case_id)
        assert persisted is not None
        assert persisted.is_test is True
        # Going live affects only cases created after this point.
        uow.businesses.update_reporting_settings(
            "acme-home-services", test_mode_enabled=False
        )
        uow.commit()
    with uow_factory() as uow:
        rehydrated = uow.cases.get("acme-home-services", result.case_id)
        assert rehydrated is not None and rehydrated.is_test is True
    live_result = intake.receive(intake_message("after-go-live", phone="+1 312 555 0199"))
    with uow_factory() as uow:
        live_case = uow.cases.get("acme-home-services", live_result.case_id)
        assert live_case is not None and live_case.is_test is False


def test_reporting_baseline_is_reversible_without_deleting_case_audit(uow_factory) -> None:
    seed_business(uow_factory)
    case = ProcessCase("baseline-case", "acme-home-services", Lead("baseline-lead", "Ada"), created_at=NOW)
    audit_event = ProcessEvent("AUDIT_RETAINED", occurred_at=NOW)
    case.record(audit_event)
    with uow_factory() as uow:
        uow.leads.add(case.business_id, case.lead, case.created_at)
        uow.cases.add(case)
        uow.events.add(case.business_id, case.case_id, audit_event)
        changed = uow.businesses.update_reporting_settings(
            case.business_id, stats_since=NOW.replace(day=NOW.day + 1)
        )
        uow.commit()
        assert changed.stats_since is not None
    with uow_factory() as uow:
        retained = uow.cases.get(case.business_id, case.case_id)
        assert retained is not None
        assert [event.event_type for event in retained.event_history] == ["AUDIT_RETAINED"]
        restored = uow.businesses.update_reporting_settings(
            case.business_id, clear_stats_since=True
        )
        uow.commit()
        assert restored.stats_since is None


def test_persisted_idempotency_collision_is_explicit(uow_factory) -> None:
    seed_business(uow_factory)
    intake = make_intake(uow_factory, {"collision": qualifying_intent()})
    intake.receive(intake_message("collision"))
    with pytest.raises(IdempotencyCollisionError):
        intake.receive(intake_message("collision", raw_text="different content"))


def test_duplicate_result_is_stable_after_business_dna_changes(uow_factory) -> None:
    seed_business(uow_factory)
    intake = make_intake(uow_factory, {"stable-replay": qualifying_intent()})
    message = intake_message("stable-replay")
    first = intake.receive(message)
    changed = dna()
    changed["communication"]["channels"] = ["email"]
    changed["communication"]["default_channel"] = "email"
    with uow_factory() as uow:
        uow.business_dna.add_version("acme-home-services", changed)
        uow.commit()

    duplicate = intake.receive(message)
    assert duplicate.duplicate
    assert duplicate.case_id == first.case_id


def test_existing_persisted_lead_progresses_after_restart(uow_factory) -> None:
    seed_business(uow_factory)
    first_service = make_intake(uow_factory, {
        "restart-1": qualifying_intent(),
    })
    first_message = intake_message("restart-1", phone=None)
    first = first_service.receive(first_message)
    assert first.current_state is ProcessState.QUALIFYING

    second_service = make_intake(uow_factory, {"restart-2": IntentResult(confidence=0.95)})
    second = second_service.receive(intake_message(
        "restart-2", phone="+1 312 555 0100", case_id=first.case_id
    ))
    assert second.case_id == first.case_id
    assert second.current_state is ProcessState.QUALIFIED

    replay = first_service.receive(first_message)
    assert replay.duplicate
    assert replay.case_id == first.case_id
    assert replay.current_state is ProcessState.QUALIFYING


def test_table_counts_are_tenant_data_not_process_memory(uow_factory) -> None:
    seed_business(uow_factory)
    intake = make_intake(uow_factory, {"counts": qualifying_intent()})
    intake.receive(intake_message("counts"))
    with uow_factory() as uow:
        assert uow.session.scalar(select(func.count()).select_from(LeadRow)) == 1
        assert uow.session.scalar(select(func.count()).select_from(ProcessCaseRow)) == 1
        assert uow.session.scalar(select(func.count()).select_from(ProcessEventRow)) > 0


class FailingPersistentExtractor:
    def extract(self, message: IncomingMessage, business_dna: dict) -> IntentResult:
        raise RuntimeError("intent extraction failed")


def test_persistent_intake_failure_rolls_back_claim_lead_case_and_events(uow_factory) -> None:
    seed_business(uow_factory)
    service = PersistentLeadIntakeService(
        uow_factory,
        FailingPersistentExtractor(),
        DeterministicQuestionGenerator(),
    )
    with pytest.raises(RuntimeError, match="intent extraction failed"):
        service.receive(intake_message("rollback-intake"))

    with uow_factory() as uow:
        assert uow.session.scalar(select(func.count()).select_from(LeadRow)) == 0
        assert uow.session.scalar(select(func.count()).select_from(ProcessCaseRow)) == 0
        assert uow.session.scalar(select(func.count()).select_from(ProcessEventRow)) == 0
        assert uow.session.scalar(select(func.count()).select_from(ProcessedMessageRow)) == 0
