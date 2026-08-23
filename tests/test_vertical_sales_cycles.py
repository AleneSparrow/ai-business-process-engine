"""Cross-vertical acceptance matrix for the universal lead qualification cycle.

These tests intentionally do not judge an LLM's semantic accuracy. They verify
the deterministic contract around it: a zero-config onboarding can describe a
wide range of sales businesses, an evidenced catalog choice is accepted, a
complete lead qualifies, and an urgent lead is routed to a person. Model
quality belongs in a separately scored live eval so a provider regression
cannot be confused with a business-rule regression.
"""

from dataclasses import dataclass
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from src.ai.adapters import AIIntentExtractor
from src.ai.models import IntentOutput
from src.domain.business_dna_builder import OnboardingInput, OnboardingService, build_business_dna
from src.domain.models import Lead
from src.domain.qualification import IntentResult, Urgency
from src.domain.states import ProcessState
from src.engine.qualification_service import QualificationService


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "config" / "business_dna.schema.json").read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class Vertical:
    industry: str
    service: str
    description: str
    customer_message: str
    evidence: str
    question: str
    answer: str
    local: bool = False


VERTICALS = (
    Vertical("Financial planning", "Retirement planning", "Retirement income and investment planning", "I need a plan for retiring in ten years", "retiring in ten years", "What is your planning horizon?", "ten years"),
    Vertical("Real estate", "Buyer representation", "Home search, offers, and purchase representation", "We want help buying our first house", "buying our first house", "What type of property are you looking for?", "house"),
    Vertical("Legal services", "Initial consultation", "Family, contract, and civil legal consultations", "I need to speak with a lawyer about a custody agreement", "custody agreement", "What type of matter do you need help with?", "custody agreement"),
    Vertical("Home repair", "Repair estimate", "Diagnosis and estimates for residential repairs", "Our ceiling is leaking after the storm", "ceiling is leaking", "What needs to be repaired?", "ceiling", local=True),
    Vertical("Taxi and private hire", "Airport transfer", "Pre-booked passenger transport to and from airports", "I need a ride to the airport tomorrow morning", "ride to the airport", "How many passengers are traveling?", "two", local=True),
    Vertical("Beauty services", "Hair color appointment", "Salon consultation and hair coloring", "I'd like to book balayage for my hair", "book balayage", "What result are you hoping for?", "balayage", local=True),
    Vertical("Psychology", "Therapy consultation", "Initial consultation for individual therapy", "I am looking for help with anxiety", "help with anxiety", "Are you seeking individual or couples support?", "individual"),
    Vertical("Primary care", "New patient visit", "Non-emergency primary care appointment intake", "I need a new doctor for an ongoing cough", "ongoing cough", "Are you a new or returning patient?", "new"),
    Vertical("Dentistry", "Dental consultation", "Routine and restorative dental consultations", "One of my teeth hurts when I chew", "teeth hurts", "Is this for a new or existing patient?", "new", local=True),
    Vertical("Procurement consulting", "Supplier sourcing", "B2B supplier discovery and procurement support", "We need a new packaging supplier for our factory", "packaging supplier", "What category are you sourcing?", "packaging"),
    Vertical("Wholesale sales", "Wholesale account", "Product sourcing and wholesale account onboarding", "Our stores want to carry your skincare line", "carry your skincare line", "How many locations do you operate?", "twelve"),
    Vertical("Advertising", "Campaign strategy", "Paid media campaign planning and management", "We need more qualified leads from Google Ads", "leads from Google Ads", "What is the campaign objective?", "qualified leads"),
    Vertical("Insurance brokerage", "Business insurance review", "Commercial coverage needs analysis", "I need liability coverage for my restaurant", "liability coverage", "What type of business needs coverage?", "restaurant"),
    Vertical("Accounting", "Tax preparation", "Personal and small-business tax preparation", "I need help filing taxes for my LLC", "taxes for my LLC", "Which tax year do you need help with?", "2025"),
    Vertical("Business consulting", "Growth consultation", "Strategy and operations consulting for growing companies", "Our company needs a plan to expand into two states", "expand into two states", "What is your primary growth goal?", "expansion"),
    Vertical("Education", "Tutoring assessment", "One-to-one academic tutoring and learning plans", "My daughter needs help with high school algebra", "high school algebra", "Which subject needs support?", "algebra"),
    Vertical("Auto repair", "Vehicle diagnostic", "Inspection and diagnosis of vehicle problems", "My car shakes when I brake", "shakes when I brake", "What is the vehicle make and model?", "Honda Civic", local=True),
    Vertical("Cleaning services", "Cleaning quote", "Residential and commercial cleaning estimates", "We need a deep clean before moving out", "deep clean", "What type of property is it?", "apartment", local=True),
    Vertical("Freight and logistics", "Freight quote", "Domestic freight planning and carrier sourcing", "We ship four pallets from Dallas to Miami each week", "four pallets", "What are you shipping?", "pallets"),
    Vertical("Recruiting", "Hiring consultation", "Candidate sourcing and recruitment campaigns", "We need to hire three senior engineers", "three senior engineers", "Which role are you hiring for?", "engineers"),
    Vertical("Managed IT", "IT support assessment", "Managed IT, cloud, and cybersecurity support", "Our twenty-person office needs outsourced IT support", "outsourced IT support", "How many users need support?", "twenty"),
    Vertical("Security systems", "Security installation quote", "Alarm, access control, and camera installation", "We need cameras for our warehouse", "cameras for our warehouse", "What type of property needs protection?", "warehouse", local=True),
    Vertical("Event planning", "Event planning consultation", "Planning and vendor coordination for private and corporate events", "We are planning a company dinner for 150 people", "company dinner", "How many guests do you expect?", "150"),
    Vertical("Photography", "Photography booking", "Commercial, event, and portrait photography", "We need a photographer for our product launch", "product launch", "What type of shoot is this?", "product launch", local=True),
    Vertical("Veterinary services", "Veterinary appointment", "Non-emergency pet examinations and consultations", "My dog needs a routine checkup", "routine checkup", "What kind of pet is the appointment for?", "dog", local=True),
    Vertical("Fitness", "Personal training consultation", "Personal training programs and fitness assessments", "I want coaching to prepare for my first marathon", "first marathon", "What is your primary fitness goal?", "marathon"),
    Vertical("Travel services", "Trip planning", "Custom itinerary and travel booking support", "We want to plan a family trip to Japan", "family trip to Japan", "Where would you like to travel?", "Japan"),
    Vertical("Solar installation", "Solar assessment", "Residential solar design and installation estimates", "I want to know if solar makes sense for my house", "solar makes sense", "What type of property is this?", "house", local=True),
    Vertical("Pest control", "Pest inspection", "Inspection and treatment planning for household pests", "We keep finding termites near the garage", "finding termites", "Which pest have you noticed?", "termites", local=True),
    Vertical("Landscaping", "Landscape estimate", "Landscape design and recurring yard maintenance", "We need a drought-tolerant backyard redesign", "backyard redesign", "What type of project are you considering?", "redesign", local=True),
    Vertical("HVAC", "HVAC diagnostic", "Heating and cooling diagnosis and repair", "Our air conditioner is blowing warm air", "blowing warm air", "Which system needs service?", "air conditioner", local=True),
    Vertical("Plumbing", "Plumbing repair", "Residential plumbing diagnosis and repair", "The kitchen pipe is leaking under the sink", "pipe is leaking", "What plumbing issue are you experiencing?", "leaking", local=True),
    Vertical("Roofing", "Roof inspection", "Roof inspections, repairs, and replacement estimates", "The storm tore shingles off our roof", "shingles off our roof", "What happened to the roof?", "storm", local=True),
    Vertical("Moving services", "Moving quote", "Local and long-distance household moving estimates", "We are moving a two-bedroom apartment next month", "moving a two-bedroom apartment", "What size home are you moving?", "two-bedroom", local=True),
    Vertical("Property management", "Management consultation", "Residential rental management for property owners", "I need someone to manage six rental units", "manage six rental units", "How many units need management?", "six"),
    Vertical("Mortgage brokerage", "Mortgage consultation", "Home purchase and refinance loan guidance", "We want preapproval before making an offer", "preapproval", "Is this a purchase or refinance?", "purchase"),
    Vertical("Commercial equipment", "Equipment quote", "B2B equipment selection and sales", "Our bakery needs a new commercial oven", "commercial oven", "What equipment do you need?", "oven"),
    Vertical("SaaS sales", "Product demo", "Business software demos and solution consultations", "We need software to automate customer onboarding", "automate customer onboarding", "How many people will use the software?", "forty"),
    Vertical("Marketing agency", "Marketing consultation", "Brand, content, and demand generation services", "We need a launch strategy for a new mobile app", "launch strategy", "What are you promoting?", "mobile app"),
    Vertical("Medical specialty clinic", "Specialist consultation", "Non-emergency specialist appointment intake", "I need a consultation about recurring migraines", "recurring migraines", "Are you a new or returning patient?", "new", local=True),
)


def _dna(vertical: Vertical) -> dict:
    return build_business_dna(OnboardingInput(
        business_id=f"vertical-{VERTICALS.index(vertical)}",
        business_name=f"QA {vertical.industry}",
        industry=vertical.industry,
        description=vertical.description,
        tone="Friendly & direct",
        services=(OnboardingService(vertical.service, (vertical.question,), vertical.description),),
        service_zip_codes=("10001",) if vertical.local else (),
        enforce_service_area=vertical.local,
    ))


def _intent_output(service_id: str, evidence: str) -> IntentOutput:
    return IntentOutput.model_validate({
        "service_id": service_id,
        "unsupported_service": False,
        "unsupported_service_name": None,
        "service_evidence": evidence,
        "urgency": "normal",
        "customer_location": None,
        "preferred_time": None,
        "notes": None,
        "customer_name": None,
        "phone": None,
        "email": None,
        "confidence": 0.95,
        "requires_human": False,
        "unintelligible": False,
        "qualification_answers": [],
        "objection_phrase": None,
        "customer_tone": "neutral",
    })


@pytest.mark.parametrize("vertical", VERTICALS, ids=lambda value: value.industry)
def test_vertical_onboarding_and_complete_lead_cycle(vertical: Vertical) -> None:
    dna = _dna(vertical)
    Draft202012Validator(SCHEMA).validate(dna)

    service = dna["services"][0]
    resolved = AIIntentExtractor._resolve_service(
        _intent_output(service["id"], vertical.evidence),
        [{
            "id": service["id"],
            "name": service["name"],
            "description": service["description"],
            "aliases": service["intake_keywords"],
            "qualification_questions": service["qualification_questions"],
        }],
        vertical.customer_message,
    )
    assert resolved == service["id"]

    question_id = service["qualification_questions"][0]["id"]
    result = QualificationService().evaluate(
        Lead("lead-1", name="Test Customer", phone="+1 212 555 0100"),
        IntentResult(
            service_requested=resolved,
            urgency=Urgency.NORMAL,
            customer_location="10001" if vertical.local else None,
            confidence=0.95,
            qualification_answers={question_id: vertical.answer},
        ),
        dna,
    )

    assert result.qualified
    assert result.recommended_next_state is ProcessState.QUALIFIED
    assert result.service_id == service["id"]
    assert not result.booking_allowed  # zero-config never books without owner approval


@pytest.mark.parametrize("vertical", VERTICALS, ids=lambda value: value.industry)
def test_every_vertical_escalates_emergency_instead_of_automating(vertical: Vertical) -> None:
    dna = _dna(vertical)
    service_id = dna["services"][0]["id"]
    result = QualificationService().evaluate(
        Lead("lead-emergency", name="Test Customer", phone="+1 212 555 0101"),
        IntentResult(service_requested=service_id, urgency=Urgency.EMERGENCY, confidence=0.95),
        dna,
    )

    assert result.recommended_next_state is ProcessState.NEEDS_HUMAN
    assert result.requires_human
    assert not result.booking_allowed
