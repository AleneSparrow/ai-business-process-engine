"""Zero-config fallback matching: everyday wording without a live model."""

from datetime import datetime, timezone

from src.domain.business_dna_builder import OnboardingInput, OnboardingService, build_business_dna
from src.domain.qualification import IncomingMessage
from src.engine.intent_extractor import DeterministicIntentExtractor


NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _northstar() -> dict:
    return build_business_dna(OnboardingInput(
        business_id="northstar-home",
        business_name="Northstar Home Services",
        industry="Residential home services",
        description="Residential heating, cooling, plumbing, drain, and electrical repair",
        tone="Friendly & direct",
        services=(
            OnboardingService(
                "Heating & AC repair",
                ("Is the system running at all?",),
                "Furnace not heating, AC not cooling, noisy HVAC, thermostat and airflow problems",
            ),
            OnboardingService(
                "Plumbing repair",
                ("Is water currently leaking?",),
                "Leaking pipes, faucets, toilets, low water pressure, and general plumbing faults",
            ),
            OnboardingService(
                "Drain cleaning",
                ("Which drain is affected?",),
                "Slow or blocked sinks, tubs, showers, and sewer or drain backups",
            ),
            OnboardingService(
                "Electrical troubleshooting",
                ("Do you see sparks, smoke, or exposed wiring?",),
                "Outlets, switches, lights, breakers, and intermittent power faults",
            ),
        ),
        service_zip_codes=("10001", "10002"),
    ))


def _incoming(text: str) -> IncomingMessage:
    return IncomingMessage(
        business_id="northstar-home",
        channel="webchat",
        external_message_id="eval-1",
        raw_text=text,
        timestamp=NOW,
    )


def test_furnace_wording_selects_hvac_without_catalog_name() -> None:
    intent = DeterministicIntentExtractor().extract(
        _incoming("My furnace keeps making a rattling noise and the house isn't warming up."),
        _northstar(),
    )
    assert intent.service_requested == "heating-ac-repair"
    assert not intent.requires_human


def test_kitchen_sink_backup_selects_drain_cleaning() -> None:
    intent = DeterministicIntentExtractor().extract(
        _incoming("The kitchen sink takes forever to empty and water comes back up."),
        _northstar(),
    )
    assert intent.service_requested == "drain-cleaning"


def test_toilet_leak_selects_plumbing() -> None:
    intent = DeterministicIntentExtractor().extract(
        _incoming("The toilet is leaking."),
        _northstar(),
    )
    assert intent.service_requested == "plumbing-repair"


def test_shared_repair_word_does_not_guess_between_services() -> None:
    intent = DeterministicIntentExtractor().extract(
        _incoming("Can you repair my laptop?"),
        _northstar(),
    )
    assert intent.service_requested is None


def test_introduced_name_is_read_without_my_name_is() -> None:
    intent = DeterministicIntentExtractor().extract(
        _incoming("I'm Sam, at 10002. You can reach me at +1 212-555-0101."),
        _northstar(),
    )
    assert intent.customer_name == "Sam"
    assert intent.customer_location == "10002"
    assert intent.phone is not None


def test_im_really_worried_is_not_treated_as_a_name() -> None:
    intent = DeterministicIntentExtractor().extract(
        _incoming("I'm really worried. The furnace stopped."),
        _northstar(),
    )
    assert intent.customer_name is None
    assert intent.service_requested == "heating-ac-repair"


def test_breaker_panel_smoking_is_an_emergency() -> None:
    intent = DeterministicIntentExtractor().extract(
        _incoming("The breaker panel is smoking and I can see sparks."),
        _northstar(),
    )
    assert intent.urgency.value == "emergency"
    assert intent.service_requested == "electrical-troubleshooting"


def test_return_guarantee_requests_a_human() -> None:
    dna = build_business_dna(OnboardingInput(
        business_id="harbor-wealth",
        business_name="Harbor Wealth",
        industry="Financial planning",
        description="Retirement planning",
        tone="Friendly & direct",
        services=(OnboardingService("Retirement planning", ("What is your planning horizon?",), "Retirement income planning"),),
        service_zip_codes=(),
        enforce_service_area=False,
    ))
    intent = DeterministicIntentExtractor().extract(
        IncomingMessage(
            business_id="harbor-wealth",
            channel="webchat",
            external_message_id="eval-2",
            raw_text="Guarantee me a 20 percent return and invest it now.",
            timestamp=NOW,
        ),
        dna,
    )
    assert intent.requires_human
    assert intent.service_requested is None
