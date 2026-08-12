"""Translates the simplified self-serve onboarding shape into a schema-valid Business DNA.

The onboarding wizard deliberately collects less than the full Business DNA
schema requires (no price, duration, or booking hours). This module bridges
that gap with one safe rule: every service defaults to
`fulfillment_type: "human_review"`. That requires no commercial configuration
at all and guarantees the engine can never auto-book or auto-price something
the owner never actually set — it will qualify and escalate correctly from
minute one. Pricing, availability, and payment configuration remain valid but
inactive defaults until an owner deliberately turns them on later.
"""

import re
from dataclasses import dataclass

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

_TONE_COPY = {
    "Friendly & direct": "friendly, direct, and concise",
    "Formal & precise": "formal, precise, and professional",
    "Casual & brief": "casual, brief, and plainspoken",
}
_DEFAULT_TONE_COPY = "friendly, concise, and professional"

_SERVICE_AREA_ID = "primary"
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")


def slugify(value: str, *, fallback: str = "item") -> str:
    slug = _SLUG_PATTERN.sub("-", value.strip().casefold()).strip("-")
    return slug or fallback


@dataclass(frozen=True, slots=True)
class OnboardingService:
    name: str
    questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("service name must not be empty")


@dataclass(frozen=True, slots=True)
class OnboardingInput:
    business_id: str
    business_name: str
    industry: str
    tone: str
    services: tuple[OnboardingService, ...]
    service_zip_codes: tuple[str, ...]
    enforce_service_area: bool = True

    def __post_init__(self) -> None:
        if not self.business_id.strip():
            raise ValueError("business_id must not be empty")
        if not self.business_name.strip():
            raise ValueError("business_name must not be empty")
        if not self.industry.strip():
            raise ValueError("industry must not be empty")
        if not self.services:
            raise ValueError("at least one service is required")
        if not self.service_zip_codes:
            raise ValueError("at least one service zip code is required")


def _build_services(services: tuple[OnboardingService, ...]) -> list[dict]:
    used_ids: set[str] = set()
    built: list[dict] = []
    for service in services:
        base_id = slugify(service.name)
        service_id = base_id
        suffix = 2
        while service_id in used_ids:
            service_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(service_id)

        questions_json = [
            {
                "id": slugify(question, fallback=f"question-{index}"),
                "prompt": question.strip(),
                "required": True,
                "disqualifying_answers": [],
            }
            for index, question in enumerate(service.questions, start=1)
            if question.strip()
        ]

        built.append({
            "id": service_id,
            "name": service.name,
            "description": service.name,
            "duration_minutes": 60,
            "fulfillment_type": "human_review",
            "pricing": {"model": "custom_quote", "tax_included": False},
            "service_area_ids": [_SERVICE_AREA_ID],
            "intake_keywords": [service.name.casefold()],
            "booking_allowed": False,
            "qualification_questions": questions_json,
        })
    return built


def build_business_dna(onboarding: OnboardingInput) -> dict:
    tone_copy = _TONE_COPY.get(onboarding.tone, _DEFAULT_TONE_COPY)
    qualification_rules = (
        [{"field": "service_area_id", "operator": "in", "value": [_SERVICE_AREA_ID], "outcome": "qualified"}]
        if onboarding.enforce_service_area
        else []
    )

    return {
        "schema_version": "1.1",
        "business": {
            "id": onboarding.business_id,
            "name": onboarding.business_name,
            "industry": onboarding.industry,
            "description": "",
            "timezone": "UTC",
            "currency": "USD",
        },
        "services": _build_services(onboarding.services),
        "service_areas": [
            {"id": _SERVICE_AREA_ID, "type": "postal_codes", "values": list(onboarding.service_zip_codes)},
        ],
        "business_hours": {
            day: [{"opens": "09:00", "closes": "17:00"}] for day in _WEEKDAYS
        },
        "customer_information": {
            "required_fields": ["name", "phone"],
            "optional_fields": ["email", "notes"],
            "field_questions": {
                "name": "What name should we use for the request?",
                "phone": "What is the best phone number to reach you?",
            },
        },
        "qualification": {
            "rules": qualification_rules,
            "default_outcome": "needs_human",
            "enforce_service_area": onboarding.enforce_service_area,
            "lost_message": (
                "Sorry, this request is outside what we currently support "
                "— we'll follow up if that changes."
            ),
        },
        "booking": {
            "enabled": False,
            "timezone": "UTC",
            "minimum_notice_minutes": 120,
            "maximum_advance_days": 60,
            "slot_interval_minutes": 30,
            "buffer_before_minutes": 15,
            "buffer_after_minutes": 15,
            "allowed_days": list(_WEEKDAYS),
            "allowed_times": [{"starts": "09:00", "ends": "17:00"}],
            "capacity": 1,
            "proposal_count": 3,
            "proposal_ttl_minutes": 30,
            "requires_confirmation": True,
            "cancellation_notice_hours": 24,
            "rescheduling": {"allowed": True, "minimum_notice_hours": 24},
            "cancellation": {"allowed": True, "minimum_notice_hours": 24},
        },
        "sales": {
            "quote_expiry_days": 14,
            "follow_up": {"delays_hours": [24, 72, 168], "maximum_attempts": 3},
        },
        "payment": {
            "currency": "USD",
            "timing": "after_service",
            "accepted_methods": ["card"],
            "deposit": {"required": False, "type": "percentage", "percentage": None, "fixed_amount": None},
            "request_expiry_hours": 72,
            "human_approval_above": "10000.00",
        },
        "communication": {
            "channels": ["webchat"],
            "default_channel": "webchat",
            "language": "English",
            "tone": tone_copy,
            "quiet_hours": {"starts": "21:00", "ends": "08:00"},
        },
        "chat_widget": {
            "enabled": True,
            "title": f"Chat with {onboarding.business_name}",
            "welcome_message": "Hi! Tell us what you need help with.",
            "qualified_message": "Thanks — we have what we need. Our team will follow up with next steps.",
            "closed_message": "This conversation is complete. Please reach out again if you need more help.",
        },
        "ai_permissions": {
            "allowed": ["classify_intent", "extract_customer_details", "draft_message"],
            "forbidden": ["issue_refund", "change_price", "capture_payment", "make_legal_commitment"],
            "minimum_confidence": 0.8,
        },
        "human_escalation": {
            "triggers": ["low_confidence", "customer_request"],
            "queue": "operations",
            "response_target_minutes": 30,
            "customer_message": "A team member needs to review your request and will follow up shortly.",
        },
        "integrations": {},
    }
