"""Harness checks for the USP dialogue eval — no live provider calls."""

import runpy
from pathlib import Path

from jsonschema import Draft202012Validator

from src.domain.states import ProcessState


ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts" / "live_usp_dialogue_eval.py"))
SCHEMA = MODULE["SCHEMA"]


def test_every_eval_business_builds_schema_valid_dna() -> None:
    for spec in MODULE["BUSINESSES"]:
        dna = MODULE["build_dna"](spec)
        Draft202012Validator(SCHEMA).validate(dna)
        assert dna["business"]["id"] == spec.business_id
        assert len(dna["services"]) == len(spec.services)


def test_zero_config_business_enables_booking_as_the_universal_close() -> None:
    spec = next(item for item in MODULE["BUSINESSES"] if item.setup == "zero_config")
    dna = MODULE["build_dna"](spec)
    assert dna["booking"]["enabled"] is True
    assert all(service["fulfillment_type"] == "bookable" for service in dna["services"])


def test_owner_settings_can_enable_booking_and_fixed_quotes() -> None:
    spec = next(item for item in MODULE["BUSINESSES"] if item.business_id == "northstar-home")
    dna = MODULE["build_dna"](spec)
    by_id = {service["id"]: service for service in dna["services"]}
    assert dna["booking"]["enabled"] is True
    assert by_id["heating-ac-repair"]["fulfillment_type"] == "bookable"
    assert by_id["drain-cleaning"]["quoting"]["fixed_price"] == "149"


def test_score_record_requires_expected_state_and_service() -> None:
    scenario = MODULE["SCENARIOS"][0]
    record = {
        "final_state": ProcessState.BOOKED.value,
        "service_requested": "heating-ac-repair",
        "requires_human": False,
        "invented_prices": [],
    }
    score = MODULE["score_record"](record, scenario)
    assert score["pass"]
    assert score["to_deal"]

    missed = dict(record, service_requested="drain-cleaning")
    assert not MODULE["score_record"](missed, scenario)["pass"]


def test_dialogue_harness_books_when_customer_uses_catalog_terms(tmp_path: Path) -> None:
    """Engine-path smoke test: deterministic matching only sees catalog terms."""
    spec = next(item for item in MODULE["BUSINESSES"] if item.business_id == "northstar-home")
    scenario = MODULE["Scenario"](
        scenario_id="smoke-catalog-heating",
        business_id="northstar-home",
        usp_claims=("to_deal",),
        first_message=(
            "I need Heating & AC repair. The furnace is rattling. "
            "I'm Sam at 10002, phone +1 212-555-0101. The unit still runs."
        ),
        expected_service="heating-ac-repair",
        expected_states=("BOOKED",),
        name="Sam",
        phone="+1 212-555-0101",
        zip_code="10002",
        answers={"is-the-system-running-at-all": "The unit still runs"},
        everyday_wording=False,
    )
    database_url = f"sqlite+pysqlite:///{tmp_path / 'smoke.db'}"
    settings = MODULE["Settings"](database_url=database_url, app_env="test", ai_provider="deterministic")
    runtime = MODULE["honest_ai_runtime"](settings)
    engine = MODULE["create_database_engine"](database_url)
    MODULE["Base"].metadata.create_all(engine)
    factory = MODULE["SQLAlchemyUnitOfWork"].factory_for_engine(engine)
    MODULE["provision"](factory, spec)
    service = MODULE["ConversationService"](
        factory,
        runtime.intent_extractor,
        runtime.question_generator,
        runtime.customer_response_generator,
        reassurance_response_generator=runtime.reassurance_response_generator,
        universal_reassurance_response_generator=runtime.universal_reassurance_response_generator,
    )
    dna = MODULE["build_dna"](spec)
    record = MODULE["run_scenario"](service, factory, spec, dna, scenario)
    engine.dispose()
    assert record.get("error") is None, record.get("error")
    assert record["score"]["pass"], record
