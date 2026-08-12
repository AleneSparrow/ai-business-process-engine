"""Deterministic Milestone 7 booking and quote demo; no external APIs."""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.domain.models import Lead, ProcessCase
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.commercial_service import CommercialWorkflowService
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


ROOT = Path(__file__).parents[1]
UTC = timezone.utc


def add_qualified_case(factory, dna: dict, service_id: str, suffix: str, now: datetime) -> str:
    lead = Lead(
        f"demo-lead-{suffix}",
        "Demo Customer",
        None,
        f"+1312555010{suffix}",
        {"service_requested": service_id, "customer_location": "60601"},
    )
    case = ProcessCase(
        f"demo-case-{suffix}",
        dna["business"]["id"],
        lead,
        ProcessState.QUALIFIED,
        now,
        now,
    )
    with factory() as uow:
        uow.leads.add(case.business_id, lead, now)
        uow.cases.add(case)
        uow.commit()
    return case.case_id


def main() -> None:
    dna = json.loads((ROOT / "config" / "business_dna.example.json").read_text())
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    now = datetime.now(UTC)
    with factory() as uow:
        uow.businesses.add(Business(dna["business"]["id"], dna["business"]["name"], now, now))
        uow.business_dna.add_version(dna["business"]["id"], dna)
        uow.commit()

    workflow = CommercialWorkflowService()
    booking_case_id = add_qualified_case(factory, dna, "diagnostic-visit", "1", now)
    booking_metadata: dict = {}
    with factory() as uow:
        booking_case = uow.cases.get(dna["business"]["id"], booking_case_id)
        proposal = workflow.initialize(
            uow, booking_case, dna, booking_metadata, occurred_at=now
        )
        uow.commit()
    print("BOOKING")
    print("System:", proposal.message_text)
    print("Customer: The second option works.")
    with factory() as uow:
        booking_case = uow.cases.get(dna["business"]["id"], booking_case_id)
        confirmed = workflow.handle_message(
            uow,
            booking_case,
            dna,
            booking_metadata,
            "The second option works",
            occurred_at=now,
        )
        uow.commit()
    print("System:", confirmed.message_text)
    if confirmed.payment_request_id:
        print("System: A deposit is prepared; no payment provider is connected.")

    quote_case_id = add_qualified_case(factory, dna, "equipment-replacement", "2", now)
    quote_metadata: dict = {}
    print("\nQUOTE")
    with factory() as uow:
        quote_case = uow.cases.get(dna["business"]["id"], quote_case_id)
        question = workflow.initialize(
            uow, quote_case, dna, quote_metadata, occurred_at=now
        )
        uow.commit()
    print("System:", question.message_text)
    print("Customer: 2")
    with factory() as uow:
        quote_case = uow.cases.get(dna["business"]["id"], quote_case_id)
        quoted = workflow.handle_message(
            uow, quote_case, dna, quote_metadata, "2", occurred_at=now
        )
        uow.commit()
    print("System:", quoted.message_text)
    print("Customer: I accept.")
    with factory() as uow:
        quote_case = uow.cases.get(dna["business"]["id"], quote_case_id)
        accepted = workflow.handle_message(
            uow, quote_case, dna, quote_metadata, "I accept", occurred_at=now
        )
        uow.commit()
    print("System:", accepted.message_text)
    print("State:", accepted.current_state)
    engine.dispose()


if __name__ == "__main__":
    main()
