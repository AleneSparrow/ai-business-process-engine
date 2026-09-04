"""Live multi-turn USP eval across different businesses and sectors.

Unlike scripts/live_vertical_eval.py (first-turn intent only), this drives the
real ConversationService path: onboarding DNA (zero-config) or a Settings-page
commercial save, then a visitor-style dialogue. Production AI is used when
AI_PROVIDER=anthropic; the deterministic fallback used in production outages is
intentionally NOT wrapped here so a provider failure cannot be scored as a
successful semantic match.

Results contain only synthetic identities and are safe to keep as an artifact.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import tempfile
from time import perf_counter
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from src.ai.adapters import (
    AICustomerResponseGenerator,
    AIIntentExtractor,
    AIQuestionGenerator,
    AIReassuranceResponseGenerator,
    AIUniversalReassuranceResponseGenerator,
)
from src.ai.anthropic_provider import AnthropicProvider
from src.ai.openai_provider import OpenAIProvider
from src.ai.provider import RetryingAIProvider
from src.ai.runtime import AIRuntimeComponents, build_ai_runtime
from src.config import Settings
from src.domain.business_dna_builder import OnboardingInput, OnboardingService, build_business_dna
from src.domain.models import utc_now
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.persistence.business_dna_settings_service import (
    BusinessDNASettingsService,
    ObjectionResponseInput,
    SettingsServiceInput,
    SettingsUpdate,
)
from src.persistence.conversation_service import ConversationService
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "config" / "business_dna.schema.json").read_text(encoding="utf-8"))
_MONEY = re.compile(r"\$\s*\d+(?:,\d{3})*(?:\.\d{2})?")

DEAL_STATES = frozenset({
    ProcessState.BOOKED.value,
    ProcessState.WON.value,
    ProcessState.PAID.value,
    ProcessState.COMPLETED.value,
})
STOP_STATES = frozenset({
    ProcessState.LOST.value,
    ProcessState.NEEDS_HUMAN.value,
    ProcessState.BOOKED.value,
    ProcessState.WON.value,
    ProcessState.PAID.value,
    ProcessState.COMPLETED.value,
    ProcessState.CANCELLED.value,
})


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    name: str
    description: str
    question: str
    commercial_path: str = "human_review"
    quote_price: str | None = None
    next_step_message: str | None = None


@dataclass(frozen=True, slots=True)
class BusinessSpec:
    business_id: str
    name: str
    industry: str
    description: str
    segment: str
    setup: str  # zero_config | owner_settings
    services: tuple[ServiceSpec, ...]
    zip_codes: tuple[str, ...] = ()
    tone: str = "Friendly & direct"
    objections: tuple[tuple[str, str], ...] = ()
    booking_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    business_id: str
    usp_claims: tuple[str, ...]
    first_message: str
    expected_service: str | None
    expected_states: tuple[str, ...]
    name: str | None = None
    phone: str | None = None
    zip_code: str | None = None
    answers: Mapping[str, str] = field(default_factory=dict)
    clarify_service: str | None = None
    quote_accept: str | None = None
    service_retry: str | None = None
    reactivate_message: str | None = None
    slot_reply: str | None = None
    expect_human: bool | None = None
    expect_lost: bool = False
    everyday_wording: bool = True
    max_turns: int = 10


BUSINESSES: tuple[BusinessSpec, ...] = (
    BusinessSpec(
        business_id="northstar-home",
        name="Northstar Home Services",
        industry="Residential home services",
        description="Residential heating, cooling, plumbing, drain, and electrical troubleshooting and repair",
        segment="local services",
        setup="owner_settings",
        zip_codes=("10001", "10002", "10003", "10009", "11201"),
        booking_enabled=True,
        objections=(
            (
                "the price is too high or the customer needs to think about it",
                "The quoted amount is fixed for this service. I can keep it ready if you want to go ahead, or a teammate can follow up.",
            ),
        ),
        services=(
            ServiceSpec(
                "Heating & AC repair",
                "Furnace not heating, air conditioner or AC not cooling, noisy HVAC, thermostat and airflow problems",
                "Is the system running at all?",
                "booking",
            ),
            ServiceSpec(
                "Plumbing repair",
                "Leaking pipes, faucets, toilets, low water pressure, and general plumbing faults",
                "Is water currently leaking?",
                "booking",
            ),
            ServiceSpec(
                "Drain cleaning",
                "Slow or blocked sinks, tubs, showers, and sewer or drain backups",
                "Which drain is affected?",
                "quote",
                quote_price="149.00",
            ),
            ServiceSpec(
                "Electrical troubleshooting",
                "Outlets, switches, lights, breakers, and intermittent power faults",
                "Do you see sparks, smoke, or exposed wiring?",
                "human_review",
            ),
        ),
    ),
    BusinessSpec(
        business_id="bloom-salon",
        name="Bloom and Blade Salon",
        industry="Beauty services",
        description="Haircuts, color, and nail appointments for walk-in and booked salon guests",
        segment="local services",
        setup="owner_settings",
        zip_codes=("94102", "94103", "94107"),
        booking_enabled=True,
        services=(
            ServiceSpec(
                "Hair color appointment",
                "Salon consultation and hair coloring including balayage and highlights",
                "What result are you hoping for?",
                "booking",
            ),
            ServiceSpec(
                "Haircut",
                "Cuts, trims, and restyles",
                "How short would you like it?",
                "booking",
            ),
        ),
    ),
    BusinessSpec(
        business_id="ridge-auto",
        name="Ridge Auto Care",
        industry="Auto repair",
        description="Inspection and repair of brakes, engines, and vehicle air conditioning",
        segment="local services",
        setup="owner_settings",
        zip_codes=("85001", "85003", "85004"),
        booking_enabled=True,
        services=(
            ServiceSpec(
                "Brake service",
                "Inspection and repair when a car shakes, squeals, or pulls while braking",
                "What is the vehicle make and model?",
                "booking",
            ),
            ServiceSpec(
                "Vehicle diagnostic",
                "Check-engine lights, unusual noises, and running problems",
                "What warning lights or symptoms do you see?",
                "booking",
            ),
        ),
    ),
    BusinessSpec(
        business_id="harbor-wealth",
        name="Harbor Wealth Advisors",
        industry="Financial planning",
        description="Retirement income, investment planning, and insurance reviews for households",
        segment="regulated",
        setup="zero_config",
        services=(
            ServiceSpec(
                "Retirement planning",
                "Retirement income and investment planning for a future retirement date",
                "What is your planning horizon?",
            ),
            ServiceSpec(
                "Insurance review",
                "Life and disability coverage needs analysis",
                "What type of coverage do you want reviewed?",
            ),
        ),
    ),
    BusinessSpec(
        business_id="brightpath-tutoring",
        name="BrightPath Tutoring",
        industry="Education",
        description="One-to-one academic tutoring and learning plans for school students",
        segment="consumer services",
        setup="owner_settings",
        booking_enabled=True,
        services=(
            ServiceSpec(
                "Math tutoring",
                "One-to-one help with algebra, geometry, and other school math",
                "Which subject needs support?",
                "booking",
            ),
            ServiceSpec(
                "Test prep",
                "SAT and ACT practice plans",
                "Which exam is this for?",
                "booking",
            ),
        ),
    ),
    BusinessSpec(
        business_id="packwright-freight",
        name="Packwright Freight",
        industry="Freight and logistics",
        description="Domestic freight planning and carrier sourcing for pallets and LTL shipments",
        segment="b2b",
        setup="owner_settings",
        services=(
            ServiceSpec(
                "Freight quote",
                "Domestic pallet and LTL freight planning between US cities",
                "What are you shipping?",
                "quote",
                quote_price="890.00",
            ),
            ServiceSpec(
                "Carrier sourcing",
                "Finding a carrier for recurring lanes",
                "How often do you ship?",
                "human_review",
            ),
        ),
    ),
    BusinessSpec(
        business_id="greenleaf-pest",
        name="GreenLeaf Pest Control",
        industry="Pest control",
        description="Inspection and treatment planning for household pests",
        segment="local services",
        setup="owner_settings",
        zip_codes=("33101", "33109", "33131"),
        booking_enabled=True,
        services=(
            ServiceSpec(
                "Pest inspection",
                "Inspection and treatment for termites, ants, and other household pests",
                "Which pest have you noticed?",
                "booking",
            ),
            ServiceSpec(
                "Rodent control",
                "Mice and rat trapping and exclusion",
                "Where have you seen activity?",
                "booking",
            ),
        ),
    ),
    BusinessSpec(
        business_id="moveright",
        name="MoveRight Movers",
        industry="Moving services",
        description="Local and long-distance household moving estimates",
        segment="local services",
        setup="owner_settings",
        zip_codes=("10001", "10002", "10003"),
        services=(
            ServiceSpec(
                "Moving quote",
                "Local and long-distance household moving for apartments and houses",
                "What size home are you moving?",
                "quote",
                quote_price="1299.00",
            ),
        ),
    ),
    BusinessSpec(
        business_id="lenslight",
        name="Lens and Light Studio",
        industry="Photography",
        description="Commercial, event, and portrait photography",
        segment="local services",
        setup="owner_settings",
        zip_codes=("90001", "90012", "90015"),
        booking_enabled=True,
        services=(
            ServiceSpec(
                "Product photography",
                "Studio and on-site photography for product launches and catalogs",
                "What type of shoot is this?",
                "booking",
            ),
            ServiceSpec(
                "Event photography",
                "Coverage for dinners, conferences, and private events",
                "How many guests do you expect?",
                "booking",
            ),
        ),
    ),
    BusinessSpec(
        business_id="cloudnest",
        name="CloudNest",
        industry="SaaS sales",
        description="Business software demos and solution consultations",
        segment="b2b",
        setup="zero_config",
        services=(
            ServiceSpec(
                "Product demo",
                "Software demos for teams that need to automate customer onboarding",
                "How many people will use the software?",
            ),
        ),
    ),
    BusinessSpec(
        business_id="pawside",
        name="Pawside Veterinary Clinic",
        industry="Veterinary services",
        description="Non-emergency pet examinations and consultations",
        segment="local services",
        setup="owner_settings",
        zip_codes=("80202", "80203", "80205"),
        booking_enabled=True,
        services=(
            ServiceSpec(
                "Veterinary appointment",
                "Routine checkups and non-emergency exams for dogs and cats",
                "What kind of pet is the appointment for?",
                "booking",
            ),
        ),
    ),
    BusinessSpec(
        business_id="sunwell",
        name="Sunwell Solar",
        industry="Solar installation",
        description="Residential solar design and installation estimates",
        segment="local services",
        setup="owner_settings",
        zip_codes=("85001", "85003", "85004"),
        services=(
            ServiceSpec(
                "Solar assessment",
                "Residential solar design and installation estimates for houses",
                "What type of property is this?",
                "quote",
                quote_price="4500.00",
            ),
        ),
    ),
    BusinessSpec(
        business_id="tidyco",
        name="TidyCo Cleaning",
        industry="Cleaning services",
        description="Residential and commercial cleaning estimates",
        segment="local services",
        setup="owner_settings",
        zip_codes=("94102", "94103", "94107"),
        services=(
            ServiceSpec(
                "Cleaning quote",
                "Deep cleaning and move-out cleaning for apartments and houses",
                "What type of property is it?",
                "quote",
                quote_price="249.00",
            ),
        ),
    ),
    BusinessSpec(
        business_id="flywheel",
        name="Flywheel",
        industry="SaaS / Software",
        description=(
            "Deterministic engine that takes an inbound inquiry all the way to a "
            "booked or quoted deal, replacing the person who processes leads"
        ),
        segment="b2b",
        setup="zero_config",
        services=(
            ServiceSpec(
                "Product demo",
                "Watch the engine take a real inbound lead from first message to a booked time or accepted quote",
                "How many inbound leads do you handle in a typical week?",
            ),
            ServiceSpec(
                "Starter trial",
                "Seven-day trial of the engine on your own inbound conversations",
                "What is the main service you sell?",
            ),
        ),
    ),
)


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        scenario_id="northstar-furnace-booking",
        business_id="northstar-home",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message=(
            "My furnace keeps making a rattling noise and the house isn't warming up. "
            "I'm Sam, at 10002. You can reach me at +1 212-555-0101. The unit still runs."
        ),
        expected_service="heating-ac-repair",
        expected_states=("BOOKED",),
        name="Sam",
        phone="+1 212-555-0101",
        zip_code="10002",
        answers={"is-the-system-running-at-all": "The unit still runs"},
    ),
    Scenario(
        scenario_id="northstar-ambiguous-then-furnace",
        business_id="northstar-home",
        usp_claims=("any_business", "zero_config_wording"),
        first_message="Something in the utility room is making a strange noise. Can somebody help?",
        expected_service="heating-ac-repair",
        expected_states=("BOOKED", "QUALIFIED", "QUALIFYING"),
        name="Sam",
        phone="+1 212-555-0106",
        zip_code="10002",
        answers={"is-the-system-running-at-all": "It still runs"},
        clarify_service="It's the furnace, and it happens whenever the heat starts.",
    ),
    Scenario(
        scenario_id="northstar-drain-quote",
        business_id="northstar-home",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message=(
            "The kitchen sink takes forever to empty and now water comes back up when the dishwasher runs."
        ),
        expected_service="drain-cleaning",
        expected_states=("WON", "FOLLOW_UP"),
        name="Jordan",
        phone="+1 212-555-0107",
        zip_code="10003",
        answers={"which-drain-is-affected": "kitchen sink"},
        quote_accept="sounds good, lets do it",
    ),
    Scenario(
        scenario_id="northstar-out-of-area",
        business_id="northstar-home",
        usp_claims=("any_business",),
        first_message=(
            "My AC isn't cooling. I'm Alex, phone +1 212-555-0102, ZIP 07030, and the system is still running."
        ),
        expected_service="heating-ac-repair",
        expected_states=("LOST",),
        name="Alex",
        phone="+1 212-555-0102",
        zip_code="07030",
        answers={"is-the-system-running-at-all": "the system is still running"},
        expect_lost=True,
    ),
    Scenario(
        scenario_id="northstar-anxious-furnace",
        business_id="northstar-home",
        usp_claims=("tone", "any_business"),
        first_message=(
            "I'm really worried. The furnace stopped and I have children in the house. "
            "Please tell me what to do. I'm Riley at 10001, +1 212-555-0104."
        ),
        expected_service="heating-ac-repair",
        expected_states=("BOOKED", "QUALIFIED", "QUALIFYING", "NEEDS_HUMAN"),
        name="Riley",
        phone="+1 212-555-0104",
        zip_code="10001",
        answers={"is-the-system-running-at-all": "It stopped"},
        everyday_wording=True,
    ),
    Scenario(
        scenario_id="northstar-electrical-emergency",
        business_id="northstar-home",
        usp_claims=("safety",),
        first_message="The breaker panel is smoking and I can see sparks.",
        expected_service=None,
        expected_states=("NEEDS_HUMAN",),
        expect_human=True,
        max_turns=2,
    ),
    Scenario(
        scenario_id="northstar-irritated-plumbing",
        business_id="northstar-home",
        usp_claims=("tone", "to_deal", "zero_config_wording"),
        first_message=(
            "I already explained this twice. The toilet is leaking, I'm in 11201, "
            "and my number is +1 718-555-0105. Just tell me when someone can come."
        ),
        expected_service="plumbing-repair",
        expected_states=("BOOKED",),
        name="Chris",
        phone="+1 718-555-0105",
        zip_code="11201",
        answers={"is-water-currently-leaking": "yes, the toilet is leaking"},
    ),
    Scenario(
        scenario_id="northstar-unsupported-laptop",
        business_id="northstar-home",
        usp_claims=("any_business",),
        first_message="Can you repair my laptop? I'm Maya at 10001, +1 212-555-0110.",
        expected_service=None,
        expected_states=("LOST",),
        name="Maya",
        phone="+1 212-555-0110",
        zip_code="10001",
        service_retry="It's my laptop that needs to be repaired.",
        expect_lost=True,
        max_turns=6,
    ),
    Scenario(
        scenario_id="salon-balayage-booking",
        business_id="bloom-salon",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="I'd like to book balayage for my hair this week.",
        expected_service="hair-color-appointment",
        expected_states=("BOOKED",),
        name="Priya",
        phone="+1 415-555-0121",
        zip_code="94102",
        answers={"what-result-are-you-hoping-for": "balayage"},
    ),
    Scenario(
        scenario_id="auto-brakes",
        business_id="ridge-auto",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="My car shakes when I brake. Can someone look at it in 85001?",
        expected_service="brake-service",
        expected_states=("BOOKED",),
        name="Diego",
        phone="+1 602-555-0131",
        zip_code="85001",
        answers={"what-is-the-vehicle-make-and-model": "Honda Civic"},
    ),
    Scenario(
        scenario_id="wealth-retirement-zero-config",
        business_id="harbor-wealth",
        usp_claims=("any_business", "zero_config", "zero_config_wording", "to_deal"),
        first_message="I need a plan for retiring in ten years. I'm in Oregon.",
        expected_service="retirement-planning",
        expected_states=("BOOKED",),
        name="Casey",
        phone="+1 503-555-0103",
        answers={"what-is-your-planning-horizon": "ten years"},
    ),
    Scenario(
        scenario_id="wealth-return-guarantee",
        business_id="harbor-wealth",
        usp_claims=("safety",),
        first_message="Guarantee me a 20 percent return and invest it now.",
        expected_service=None,
        expected_states=("NEEDS_HUMAN",),
        expect_human=True,
        max_turns=3,
    ),
    Scenario(
        scenario_id="tutoring-algebra-remote",
        business_id="brightpath-tutoring",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="My daughter needs help with high school algebra. We are in Oregon.",
        expected_service="math-tutoring",
        expected_states=("BOOKED",),
        name="Morgan",
        phone="+1 503-555-0144",
        answers={"which-subject-needs-support": "algebra"},
    ),
    Scenario(
        scenario_id="freight-pallets-quote",
        business_id="packwright-freight",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="We ship four pallets from Dallas to Miami each week.",
        expected_service="freight-quote",
        expected_states=("WON", "FOLLOW_UP"),
        name="Avery Chen",
        phone="+1 214-555-0155",
        answers={"what-are-you-shipping": "four pallets"},
        quote_accept="sounds good, lets do it",
    ),
    Scenario(
        scenario_id="northstar-ac-booking",
        business_id="northstar-home",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="Our air conditioner is blowing warm air. Can someone come to 10009?",
        expected_service="heating-ac-repair",
        expected_states=("BOOKED",),
        name="Pat",
        phone="+1 212-555-0160",
        zip_code="10009",
        answers={"is-the-system-running-at-all": "yes, it runs but blows warm air"},
    ),
    Scenario(
        scenario_id="northstar-need-it-today-still-books",
        business_id="northstar-home",
        usp_claims=("any_business", "to_deal"),
        first_message=(
            "The furnace stopped and I need it today if possible. I'm Kim at 10001, +1 212-555-0161. It is not running."
        ),
        expected_service="heating-ac-repair",
        expected_states=("BOOKED",),
        name="Kim",
        phone="+1 212-555-0161",
        zip_code="10001",
        answers={"is-the-system-running-at-all": "It is not running"},
    ),
    Scenario(
        scenario_id="northstar-invented-slot-rejected",
        business_id="northstar-home",
        usp_claims=("to_deal",),
        first_message=(
            "My furnace is rattling. I'm Lee at 10002, +1 212-555-0162. The unit still runs."
        ),
        expected_service="heating-ac-repair",
        expected_states=("QUALIFIED",),
        name="Lee",
        phone="+1 212-555-0162",
        zip_code="10002",
        answers={"is-the-system-running-at-all": "The unit still runs"},
        slot_reply="Book me tomorrow at 7:15 AM",
    ),
    Scenario(
        scenario_id="northstar-out-of-area-then-correct-zip",
        business_id="northstar-home",
        usp_claims=("any_business", "to_deal"),
        first_message=(
            "My AC isn't cooling. I'm Alex, phone +1 212-555-0163, ZIP 07030, and the system is still running."
        ),
        expected_service="heating-ac-repair",
        expected_states=("BOOKED",),
        name="Alex",
        phone="+1 212-555-0163",
        zip_code="10001",
        answers={"is-the-system-running-at-all": "the system is still running"},
        reactivate_message="Sorry, the ZIP is actually 10001.",
        max_turns=8,
    ),
    Scenario(
        scenario_id="salon-haircut-booking",
        business_id="bloom-salon",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="I need a trim, not a full restyle. I'm in 94103.",
        expected_service="haircut",
        expected_states=("BOOKED",),
        name="Jamie",
        phone="+1 415-555-0164",
        zip_code="94103",
        answers={"how-short-would-you-like-it": "just a trim"},
    ),
    Scenario(
        scenario_id="auto-check-engine",
        business_id="ridge-auto",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="The check-engine light came on this morning in 85003.",
        expected_service="vehicle-diagnostic",
        expected_states=("BOOKED",),
        name="Reese",
        phone="+1 602-555-0165",
        zip_code="85003",
        answers={"what-warning-lights-or-symptoms-do-you-see": "check-engine light"},
    ),
    Scenario(
        scenario_id="auto-out-of-area",
        business_id="ridge-auto",
        usp_claims=("any_business",),
        first_message="My car shakes when I brake. I'm in 99999. I'm Taylor, +1 602-555-0166.",
        expected_service="brake-service",
        expected_states=("LOST",),
        name="Taylor",
        phone="+1 602-555-0166",
        zip_code="99999",
        answers={"what-is-the-vehicle-make-and-model": "Toyota Camry"},
        expect_lost=True,
    ),
    Scenario(
        scenario_id="pest-termites",
        business_id="greenleaf-pest",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="We keep finding termites near the garage in 33101.",
        expected_service="pest-inspection",
        expected_states=("BOOKED",),
        name="Drew",
        phone="+1 305-555-0167",
        zip_code="33101",
        answers={"which-pest-have-you-noticed": "termites"},
    ),
    Scenario(
        scenario_id="moving-two-bedroom-quote",
        business_id="moveright",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="We are moving a two-bedroom apartment next month from 10002.",
        expected_service="moving-quote",
        expected_states=("WON", "FOLLOW_UP"),
        name="Quinn",
        phone="+1 212-555-0168",
        zip_code="10002",
        answers={"what-size-home-are-you-moving": "two-bedroom"},
        quote_accept="sounds good, lets do it",
    ),
    Scenario(
        scenario_id="photo-product-launch",
        business_id="lenslight",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="We need a photographer for our product launch in 90012.",
        expected_service="product-photography",
        expected_states=("BOOKED",),
        name="Sasha",
        phone="+1 213-555-0169",
        zip_code="90012",
        answers={"what-type-of-shoot-is-this": "product launch"},
    ),
    Scenario(
        scenario_id="saas-onboarding-zero-config",
        business_id="cloudnest",
        usp_claims=("any_business", "zero_config", "zero_config_wording", "to_deal"),
        first_message="We need software to automate customer onboarding for a forty-person team.",
        expected_service="product-demo",
        expected_states=("BOOKED",),
        name="Riley Park",
        phone="+1 415-555-0170",
        answers={"how-many-people-will-use-the-software": "forty"},
    ),
    Scenario(
        scenario_id="saas-greeting-stays-qualifying",
        business_id="cloudnest",
        usp_claims=("zero_config",),
        first_message="Hi, can you help me?",
        expected_service=None,
        expected_states=("QUALIFYING",),
        max_turns=2,
    ),
    Scenario(
        scenario_id="vet-dog-checkup",
        business_id="pawside",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="My dog needs a routine checkup. We are in 80202.",
        expected_service="veterinary-appointment",
        expected_states=("BOOKED",),
        name="Cameron",
        phone="+1 303-555-0171",
        zip_code="80202",
        answers={"what-kind-of-pet-is-the-appointment-for": "dog"},
    ),
    Scenario(
        scenario_id="solar-house-quote",
        business_id="sunwell",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="I want to know if solar makes sense for my house in 85003.",
        expected_service="solar-assessment",
        expected_states=("WON", "FOLLOW_UP"),
        name="Avery",
        phone="+1 602-555-0172",
        zip_code="85003",
        answers={"what-type-of-property-is-this": "house"},
        quote_accept="sounds good, lets do it",
    ),
    Scenario(
        scenario_id="cleaning-move-out-quote",
        business_id="tidyco",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="We need a deep clean before moving out of our apartment in 94107.",
        expected_service="cleaning-quote",
        expected_states=("WON", "FOLLOW_UP"),
        name="Emerson",
        phone="+1 415-555-0173",
        zip_code="94107",
        answers={"what-type-of-property-is-it": "apartment"},
        quote_accept="sounds good, lets do it",
    ),
    Scenario(
        scenario_id="wealth-insurance-review",
        business_id="harbor-wealth",
        usp_claims=("any_business", "zero_config", "zero_config_wording", "to_deal"),
        first_message="I need life coverage reviewed for my family.",
        expected_service="insurance-review",
        expected_states=("BOOKED",),
        name="Blake",
        phone="+1 503-555-0174",
        answers={"what-type-of-coverage-do-you-want-reviewed": "life"},
    ),
    Scenario(
        scenario_id="tutoring-sat",
        business_id="brightpath-tutoring",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="My son needs SAT practice starting next month.",
        expected_service="test-prep",
        expected_states=("BOOKED",),
        name="Harper",
        phone="+1 503-555-0175",
        answers={"which-exam-is-this-for": "SAT"},
    ),
    Scenario(
        scenario_id="freight-carrier-sourcing",
        business_id="packwright-freight",
        usp_claims=("any_business", "zero_config_wording"),
        first_message="We need a carrier for a recurring Dallas to Miami lane.",
        expected_service="carrier-sourcing",
        expected_states=("NEEDS_HUMAN", "QUALIFIED"),
        name="Jordan Hale",
        phone="+1 214-555-0176",
        answers={"how-often-do-you-ship": "weekly"},
    ),
    Scenario(
        scenario_id="pest-mice",
        business_id="greenleaf-pest",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="We have mice in the kitchen in 33109.",
        expected_service="rodent-control",
        expected_states=("BOOKED",),
        name="Finley",
        phone="+1 305-555-0177",
        zip_code="33109",
        answers={"where-have-you-seen-activity": "kitchen"},
    ),
    Scenario(
        scenario_id="photo-event",
        business_id="lenslight",
        usp_claims=("any_business", "to_deal", "zero_config_wording"),
        first_message="We need coverage for a company dinner for 150 people in 90015.",
        expected_service="event-photography",
        expected_states=("BOOKED",),
        name="Rowan",
        phone="+1 213-555-0178",
        zip_code="90015",
        answers={"how-many-guests-do-you-expect": "150"},
    ),
    Scenario(
        scenario_id="flywheel-sells-itself-demo",
        business_id="flywheel",
        usp_claims=("any_business", "to_deal", "zero_config", "zero_config_wording"),
        first_message=(
            "We lose people after they fill out the form. I need the conversation "
            "to go all the way to a booking without someone on my team handling each lead."
        ),
        expected_service="product-demo",
        expected_states=("BOOKED",),
        name="Alena",
        phone="+1 415-555-0188",
        answers={"how-many-inbound-leads-do-you-handle-in-a-typical-week": "about forty"},
    ),
)


def load_dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, rest = line.partition("=")
        values[key.strip()] = rest.strip().strip("'").strip('"')
    return values


def apply_env_file(path: Path) -> None:
    for key, value in load_dotenv_values(path).items():
        if key and key not in os.environ:
            os.environ[key] = value


def _service_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().casefold()).strip("-")


def build_dna(spec: BusinessSpec) -> dict[str, Any]:
    onboarding = OnboardingInput(
        business_id=spec.business_id,
        business_name=spec.name,
        industry=spec.industry,
        description=spec.description,
        tone=spec.tone,
        services=tuple(
            OnboardingService(item.name, (item.question,), item.description)
            for item in spec.services
        ),
        service_zip_codes=spec.zip_codes,
        enforce_service_area=bool(spec.zip_codes),
    )
    dna = build_business_dna(onboarding)
    if spec.setup == "zero_config":
        Draft202012Validator(SCHEMA).validate(dna)
        return dna
    timezone = str(dna["business"]["timezone"])
    update = SettingsUpdate(
        name=spec.name,
        industry=spec.industry,
        tone=dna["communication"]["tone"],
        services=tuple(
            SettingsServiceInput(
                id=_service_id(item.name),
                name=item.name,
                questions=(item.question,),
                description=item.description,
                commercial_path=item.commercial_path,
                quote_price=item.quote_price,
                next_step_message=item.next_step_message,
            )
            for item in spec.services
        ),
        service_zip_codes=spec.zip_codes,
        escalate_on_high_urgency=False,
        escalate_on_emergency=True,
        booking_enabled=spec.booking_enabled,
        booking_timezone=timezone,
        objection_responses=tuple(
            ObjectionResponseInput(trigger, response) for trigger, response in spec.objections
        ),
    )
    configured = BusinessDNASettingsService._apply(dna, update)
    Draft202012Validator(SCHEMA).validate(configured)
    return configured


def provision(factory, spec: BusinessSpec) -> dict[str, Any]:
    dna = build_dna(spec)
    now = utc_now()
    with factory() as uow:
        uow.businesses.add(Business(spec.business_id, spec.name, now, now))
        uow.business_dna.add_version(spec.business_id, dna)
        uow.commit()
    return dna


def honest_ai_runtime(settings: Settings) -> AIRuntimeComponents:
    """Production adapters without the outage fallback, so eval scores stay honest."""
    if settings.ai_provider == "deterministic":
        return build_ai_runtime(settings)
    if settings.ai_provider == "anthropic":
        if settings.anthropic_api_key is None or settings.anthropic_model is None:
            raise RuntimeError("Anthropic runtime configuration is incomplete")
        provider = RetryingAIProvider(
            AnthropicProvider(
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model,
                timeout_seconds=settings.ai_timeout_seconds,
            ),
            max_retries=settings.ai_max_retries,
        )
        model_name = settings.anthropic_model
        provider_name = "anthropic"
    elif settings.ai_provider == "openai":
        if settings.openai_api_key is None or settings.openai_model is None:
            raise RuntimeError("OpenAI runtime configuration is incomplete")
        provider = RetryingAIProvider(
            OpenAIProvider(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                timeout_seconds=settings.ai_timeout_seconds,
            ),
            max_retries=settings.ai_max_retries,
        )
        model_name = settings.openai_model
        provider_name = "openai"
    else:
        raise RuntimeError(f"unsupported AI_PROVIDER: {settings.ai_provider}")
    return AIRuntimeComponents(
        AIIntentExtractor(provider),
        AIQuestionGenerator(provider),
        AICustomerResponseGenerator(provider),
        AIReassuranceResponseGenerator(provider),
        AIUniversalReassuranceResponseGenerator(provider),
        provider_name,
        model_name,
    )


def _inspect(factory, business_id: str, token: str) -> dict[str, Any]:
    token_hash = ConversationService.hash_token(token)
    with factory() as uow:
        conversation = uow.conversations.get_by_token_hash(business_id, token_hash)
        if conversation is None:
            return {"unresolved": [], "service_requested": None, "case_state": None}
        unresolved = [str(item) for item in conversation.metadata.get("unresolved_items", [])]
        service_requested = None
        case_state = conversation.metadata.get("current_state")
        if conversation.case_id is not None:
            case = uow.cases.get(business_id, conversation.case_id)
            if case is not None:
                case_state = case.current_state.value
                service_requested = case.lead.attributes.get("service_requested")
        return {
            "unresolved": unresolved,
            "service_requested": service_requested,
            "case_state": case_state,
        }


def _assistant_text(snapshot) -> str:
    for message in reversed(snapshot.messages):
        if message.role.value == "assistant":
            return message.text
    return ""


def _configured_prices(dna: Mapping[str, Any]) -> set[str]:
    prices: set[str] = set()
    for service in dna.get("services", []):
        if not isinstance(service, Mapping):
            continue
        quoting = service.get("quoting")
        if isinstance(quoting, Mapping) and quoting.get("fixed_price") is not None:
            prices.add(f"{quoting['fixed_price']}")
    return prices


def _money_key(value: str) -> str:
    return format(Decimal(value.replace("$", "").replace(",", "").strip()), "f")


def _invented_prices(text: str, allowed: set[str]) -> list[str]:
    allowed_keys = {_money_key(item) for item in allowed}
    found: list[str] = []
    for match in _MONEY.findall(text):
        try:
            key = _money_key(match)
        except Exception:
            found.append(match)
            continue
        if key not in allowed_keys:
            found.append(match)
    return found


def _contains_catalog_name(message: str, dna: Mapping[str, Any]) -> bool:
    text = message.casefold()
    for service in dna.get("services", []):
        name = str(service.get("name", "")).casefold()
        if name and name in text:
            return True
    return False


def choose_reply(
    scenario: Scenario,
    *,
    state: str | None,
    unresolved: list[str],
    last_text: str,
    has_slots: bool,
    has_quote: bool,
    sent: set[str],
    service_requested: str | None,
) -> str | None:
    if state == ProcessState.LOST.value:
        if scenario.reactivate_message and "reactivate" not in sent:
            sent.add("reactivate")
            return scenario.reactivate_message
        return None
    if state == ProcessState.NEEDS_HUMAN.value:
        return None
    if state in DEAL_STATES:
        return None
    if state in STOP_STATES and not (state == ProcessState.QUOTED.value and scenario.quote_accept):
        return None
    if state == ProcessState.QUOTED.value and scenario.quote_accept and "quote_accept" not in sent:
        sent.add("quote_accept")
        return scenario.quote_accept
    if state in {ProcessState.QUALIFIED.value, ProcessState.QUOTED.value} and has_slots and "slot" not in sent:
        sent.add("slot")
        return scenario.slot_reply or "The second option works"
    if state == ProcessState.QUALIFIED.value and has_quote and scenario.quote_accept and "quote_accept" not in sent:
        sent.add("quote_accept")
        return scenario.quote_accept
    if scenario.clarify_service and not service_requested and "clarify" not in sent:
        sent.add("clarify")
        return scenario.clarify_service
    if "field:service_id" in unresolved and scenario.service_retry and "service_retry" not in sent:
        sent.add("service_retry")
        return scenario.service_retry
    if "field:phone" in unresolved and scenario.phone and "phone" not in sent:
        sent.add("phone")
        return f"My phone is {scenario.phone}"
    if "field:name" in unresolved and scenario.name and "name" not in sent:
        sent.add("name")
        return f"My name is {scenario.name}"
    if "field:customer_location" in unresolved and scenario.zip_code and "zip" not in sent:
        sent.add("zip")
        return scenario.zip_code
    for item in unresolved:
        if item.startswith("question:"):
            question_id = item.removeprefix("question:")
            key = f"question:{question_id}"
            if key in sent:
                continue
            sent.add(key)
            if question_id in scenario.answers:
                return scenario.answers[question_id]
            if scenario.answers:
                return next(iter(scenario.answers.values()))
    lower = last_text.casefold()
    if "phone" in lower and scenario.phone and "phone" not in sent:
        sent.add("phone")
        return f"My phone is {scenario.phone}"
    if "zip" in lower and scenario.zip_code and "zip" not in sent:
        sent.add("zip")
        return scenario.zip_code
    if "name" in lower and scenario.name and "name" not in sent:
        sent.add("name")
        return f"My name is {scenario.name}"
    return None


def score_record(record: dict[str, Any], scenario: Scenario) -> dict[str, Any]:
    final_state = record.get("final_state")
    service = record.get("service_requested")
    service_ok = scenario.expected_service is None or service == scenario.expected_service
    if scenario.expected_service is None and scenario.expect_lost:
        service_ok = True
    state_ok = final_state in scenario.expected_states
    human_ok = True
    if scenario.expect_human is True:
        human_ok = bool(record.get("requires_human")) or final_state == ProcessState.NEEDS_HUMAN.value
    elif scenario.expect_human is False:
        human_ok = not record.get("requires_human")
    lost_ok = (final_state == ProcessState.LOST.value) if scenario.expect_lost else True
    invented = record.get("invented_prices") or []
    to_deal = final_state in DEAL_STATES or final_state == ProcessState.FOLLOW_UP.value
    qualified = final_state in {
        ProcessState.QUALIFIED.value,
        ProcessState.QUOTED.value,
        ProcessState.FOLLOW_UP.value,
        *DEAL_STATES,
        ProcessState.NEEDS_HUMAN.value,
    } and service_ok
    passed = bool(service_ok and state_ok and human_ok and lost_ok and not invented and not record.get("error"))
    return {
        "service_match": bool(service_ok),
        "state_match": bool(state_ok),
        "human_match": bool(human_ok),
        "lost_match": bool(lost_ok),
        "no_invented_price": not invented,
        "to_deal": bool(to_deal and service_ok),
        "reached_qualified_or_beyond": bool(qualified),
        "pass": passed,
    }


def run_scenario(
    service: ConversationService,
    factory,
    spec: BusinessSpec,
    dna: Mapping[str, Any],
    scenario: Scenario,
) -> dict[str, Any]:
    started = perf_counter()
    record: dict[str, Any] = {
        "scenario_id": scenario.scenario_id,
        "business_id": spec.business_id,
        "business_name": spec.name,
        "industry": spec.industry,
        "segment": spec.segment,
        "setup": spec.setup,
        "usp_claims": list(scenario.usp_claims),
        "everyday_wording": scenario.everyday_wording and not _contains_catalog_name(scenario.first_message, dna),
        "first_message": scenario.first_message,
        "expected_service": scenario.expected_service,
        "expected_states": list(scenario.expected_states),
        "turns": [],
    }
    sent: set[str] = set()
    allowed_prices = _configured_prices(dna)
    try:
        snapshot = service.create(
            spec.business_id,
            message_text=scenario.first_message,
            external_message_id=f"{scenario.scenario_id}-t0",
            customer_timezone="America/New_York",
        )
        token = snapshot.conversation_token
        record["turns"].append({
            "customer": scenario.first_message,
            "assistant": _assistant_text(snapshot),
            "state": snapshot.current_state.value if snapshot.current_state else None,
            "requires_human": snapshot.requires_human,
        })
        for turn in range(1, scenario.max_turns):
            inspect = _inspect(factory, spec.business_id, token)
            commercial = service.get_commercial(spec.business_id, token)
            reply = choose_reply(
                scenario,
                state=snapshot.current_state.value if snapshot.current_state else None,
                unresolved=inspect["unresolved"],
                last_text=_assistant_text(snapshot),
                has_slots=bool(commercial.proposed_slots),
                has_quote=commercial.quote is not None,
                sent=sent,
                service_requested=inspect["service_requested"],
            )
            if reply is None:
                break
            snapshot = service.send_message(
                spec.business_id,
                token,
                message_text=reply,
                external_message_id=f"{scenario.scenario_id}-t{turn}",
            )
            record["turns"].append({
                "customer": reply,
                "assistant": _assistant_text(snapshot),
                "state": snapshot.current_state.value if snapshot.current_state else None,
                "requires_human": snapshot.requires_human,
            })
        inspect = _inspect(factory, spec.business_id, token)
        commercial = service.get_commercial(spec.business_id, token)
        assistant_texts = " ".join(turn["assistant"] or "" for turn in record["turns"])
        record.update({
            "final_state": snapshot.current_state.value if snapshot.current_state else None,
            "requires_human": snapshot.requires_human,
            "service_requested": inspect["service_requested"],
            "unresolved": inspect["unresolved"],
            "has_booking": commercial.booking is not None,
            "has_quote": commercial.quote is not None,
            "slot_count": len(commercial.proposed_slots),
            "invented_prices": _invented_prices(assistant_texts, allowed_prices),
        })
        record["score"] = score_record(record, scenario)
    except Exception as exc:  # eval must record failures and continue
        record.update({
            "error_type": type(exc).__name__,
            "error": str(exc),
            "final_state": record["turns"][-1]["state"] if record["turns"] else None,
            "requires_human": False,
            "service_requested": None,
            "invented_prices": [],
        })
        record["score"] = score_record(record, scenario)
        record["score"]["pass"] = False
    record["wall_latency_ms"] = round((perf_counter() - started) * 1000)
    return record


def summarize(records: list[dict[str, Any]], provider: str, model: str) -> dict[str, Any]:
    def rate(predicate) -> float | None:
        if not records:
            return None
        return sum(bool(predicate(row)) for row in records) / len(records)

    by_segment: dict[str, dict[str, Any]] = {}
    for segment in sorted({row["segment"] for row in records}):
        rows = [row for row in records if row["segment"] == segment]
        by_segment[segment] = {
            "cases": len(rows),
            "pass_rate": sum(bool(row.get("score", {}).get("pass")) for row in rows) / len(rows),
            "service_match_rate": sum(bool(row.get("score", {}).get("service_match")) for row in rows) / len(rows),
            "to_deal_rate": sum(bool(row.get("score", {}).get("to_deal")) for row in rows) / len(rows),
        }
    by_claim: dict[str, dict[str, Any]] = {}
    for claim in sorted({claim for row in records for claim in row.get("usp_claims", [])}):
        rows = [row for row in records if claim in row.get("usp_claims", [])]
        by_claim[claim] = {
            "cases": len(rows),
            "pass_rate": sum(bool(row.get("score", {}).get("pass")) for row in rows) / len(rows),
        }
    failures = [
        {
            "scenario_id": row["scenario_id"],
            "industry": row["industry"],
            "expected_service": row.get("expected_service"),
            "service_requested": row.get("service_requested"),
            "expected_states": row.get("expected_states"),
            "final_state": row.get("final_state"),
            "error_type": row.get("error_type"),
            "error": row.get("error"),
            "score": row.get("score"),
        }
        for row in records
        if not row.get("score", {}).get("pass")
    ]
    pass_rate = rate(lambda row: row.get("score", {}).get("pass"))
    to_deal_rows = [row for row in records if "to_deal" in row.get("usp_claims", [])]
    any_business_rows = [row for row in records if "any_business" in row.get("usp_claims", [])]
    zero_config_rows = [row for row in records if "zero_config" in row.get("usp_claims", [])]
    everyday_rows = [row for row in records if row.get("everyday_wording")]
    sales_bar = 0.98
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "cases": len(records),
        "businesses": len({row["business_id"] for row in records}),
        "pass_rate": pass_rate,
        "sales_bar": sales_bar,
        "sales_bar_met": pass_rate is not None and pass_rate >= sales_bar,
        "service_match_rate": rate(lambda row: row.get("score", {}).get("service_match")),
        "state_match_rate": rate(lambda row: row.get("score", {}).get("state_match")),
        "to_deal_rate": rate(lambda row: row.get("score", {}).get("to_deal")),
        "to_deal_claim_pass_rate": (
            sum(bool(row.get("score", {}).get("pass")) for row in to_deal_rows) / len(to_deal_rows)
            if to_deal_rows else None
        ),
        "any_business_claim_pass_rate": (
            sum(bool(row.get("score", {}).get("pass")) for row in any_business_rows) / len(any_business_rows)
            if any_business_rows else None
        ),
        "zero_config_claim_pass_rate": (
            sum(bool(row.get("score", {}).get("pass")) for row in zero_config_rows) / len(zero_config_rows)
            if zero_config_rows else None
        ),
        "everyday_wording_pass_rate": (
            sum(bool(row.get("score", {}).get("pass")) for row in everyday_rows) / len(everyday_rows)
            if everyday_rows else None
        ),
        "no_invented_price_rate": rate(lambda row: row.get("score", {}).get("no_invented_price")),
        "errors": sum("error_type" in row for row in records),
        "mean_wall_latency_ms": round(sum(row["wall_latency_ms"] for row in records) / len(records)) if records else None,
        "by_segment": by_segment,
        "by_usp_claim": by_claim,
        "failures": failures,
    }


def build_settings(database_url: str, provider: str) -> Settings:
    model = os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-5"
    openai_model = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
    return Settings(
        database_url=database_url,
        app_env="test",
        ai_provider=provider,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=model if provider == "anthropic" else os.getenv("ANTHROPIC_MODEL"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=openai_model if provider == "openai" else os.getenv("OPENAI_MODEL"),
        ai_timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "45")),
        ai_max_retries=int(os.getenv("AI_MAX_RETRIES", "2")),
        public_chat_rate_limit_requests=1000,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "live-usp-dialogue-eval.json")
    parser.add_argument("--provider", choices=("anthropic", "openai", "deterministic"), default="anthropic")
    parser.add_argument("--only", action="append", default=[], help="Run only these scenario_id values.")
    args = parser.parse_args()
    apply_env_file(ROOT / ".env")
    requested_provider = args.provider
    if requested_provider == "anthropic" and not (os.getenv("ANTHROPIC_API_KEY") or "").strip():
        args.provider = "deterministic"

    selected = tuple(
        scenario for scenario in SCENARIOS
        if not args.only or scenario.scenario_id in set(args.only)
    )
    if args.only and len(selected) != len(set(args.only)):
        known = ", ".join(scenario.scenario_id for scenario in SCENARIOS)
        raise SystemExit(f"Unknown --only value. Known: {known}")

    handle = tempfile.NamedTemporaryFile(prefix="usp-eval-", suffix=".db", delete=False)
    handle.close()
    database_url = f"sqlite+pysqlite:///{handle.name}"
    settings = build_settings(database_url, args.provider)
    runtime = honest_ai_runtime(settings)
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    service = ConversationService(
        factory,
        runtime.intent_extractor,
        runtime.question_generator,
        runtime.customer_response_generator,
        reassurance_response_generator=runtime.reassurance_response_generator,
        universal_reassurance_response_generator=runtime.universal_reassurance_response_generator,
    )
    dna_by_business = {spec.business_id: provision(factory, spec) for spec in BUSINESSES}
    spec_by_id = {spec.business_id: spec for spec in BUSINESSES}
    records = [
        run_scenario(service, factory, spec_by_id[scenario.business_id], dna_by_business[scenario.business_id], scenario)
        for scenario in selected
    ]
    engine.dispose()
    Path(handle.name).unlink(missing_ok=True)
    summary = summarize(records, runtime.provider_name, runtime.model_name)
    summary["requested_provider"] = requested_provider
    summary["anthropic_available"] = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())
    payload = {"summary": summary, "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
