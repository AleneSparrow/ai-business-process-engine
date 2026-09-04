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
from src.domain.sales_opening import compose_opening_pitch
from src.domain.us_postal_timezones import (
    DEFAULT_TIMEZONE,
    timezone_for_service_area,
)

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

_TONE_COPY = {
    "Friendly & direct": "friendly, direct, and concise",
    "Formal & precise": "formal, precise, and professional",
    "Casual & brief": "casual, brief, and plainspoken",
}
_DEFAULT_TONE_COPY = "friendly, concise, and professional"
# Time zone history, in two steps.
#
# Step one (2026-08-19): the wizard has no timezone question, so every business
# got "UTC" -- which for a US product meant every fresh business quoted
# appointment times in UTC until its owner found Settings. Worse, "UTC" matched
# no <option> there and silently rendered as whichever zone was first in the
# list. Eastern replaced it: a real, DST-aware zone and a safer single default.
#
# Step two (2026-08-25): Eastern is still wrong for most of the country, and
# the zone is printed to the customer in every slot offer and booking
# confirmation. But the wizard already asks which ZIP codes the business
# serves, so the zone can be derived from an answer the owner has already
# given -- no new question, no per-business setup. See
# src/domain/us_postal_timezones.py; Eastern remains the fallback for a remote
# business or a ZIP that cannot be placed.
_DEFAULT_TIMEZONE = DEFAULT_TIMEZONE

_SERVICE_AREA_ID = "primary"
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")


def slugify(value: str, *, fallback: str = "item") -> str:
    slug = _SLUG_PATTERN.sub("-", value.strip().casefold()).strip("-")
    return slug or fallback


@dataclass(frozen=True, slots=True)
class OnboardingService:
    name: str
    questions: tuple[str, ...] = ()
    # Optional free text ("divorce, custody and child support matters").
    # Fed to the intent prompt so a customer's own wording resolves to this
    # service without the owner configuring keyword synonyms. Empty is fine --
    # the service name is used instead, which is the pre-2026-08-22 behaviour.
    description: str = ""

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
    # Empty means "no fixed service area" -- build_business_dna maps that to a
    # `remote` service area instead of `postal_codes`, so a fully online/
    # nationwide business (not just a local one) onboards cleanly.
    service_zip_codes: tuple[str, ...]
    enforce_service_area: bool = True
    # Real Urgency-based escalation triggers (see Urgency in
    # src/domain/qualification.py, consumed by QualificationService.evaluate).
    # Decision 2026-08-24 (claude/unit-economics-and-urgency-default.md,
    # variant C): defaults to False now -- a merely "high" urgency lead (a
    # leaking ceiling, "need it today") is normal, not exceptional, for most
    # verticals (roofing, plumbing, HVAC, PI law) and used to stop automation
    # exactly where speed matters most. QualificationService.evaluate still
    # always routes a HIGH-urgency lead to a human, just AFTER qualification
    # completes rather than before -- see that module for the actual
    # behavior. Setting this True opts a business back into the old
    # immediate-stop-the-cycle behavior. escalate_on_emergency is unrelated
    # and unchanged: a true emergency still escalates immediately either way.
    escalate_on_high_urgency: bool = False
    escalate_on_emergency: bool = True
    # Optional free text describing what the business does. Together with
    # `industry` this is the only per-business adaptation the intent prompt
    # receives; it lets the model read a customer's everyday wording against
    # what this business actually does. Empty is fine.
    description: str = ""

    def __post_init__(self) -> None:
        if not self.business_id.strip():
            raise ValueError("business_id must not be empty")
        if not self.business_name.strip():
            raise ValueError("business_name must not be empty")
        if not self.industry.strip():
            raise ValueError("industry must not be empty")
        if not self.services:
            raise ValueError("at least one service is required")
        if self.enforce_service_area and not self.service_zip_codes:
            raise ValueError("at least one service zip code is required when a service area is enforced")


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
            "description": service.description.strip() or service.name,
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
    # Derived from the ZIP codes the owner already typed, not asked for
    # separately -- see _DEFAULT_TIMEZONE above for why this is not left at a
    # single national constant.
    timezone = timezone_for_service_area(onboarding.service_zip_codes)
    qualification_rules = (
        [{"field": "service_area_id", "operator": "in", "value": [_SERVICE_AREA_ID], "outcome": "qualified"}]
        if onboarding.enforce_service_area
        # A remote/nationwide business has no service-area signal to gate
        # "qualified" on. By the time QualificationService._qualification_rule_outcome
        # runs, required_fields and qualification_questions completeness are
        # already verified and a real service_id is already resolved -- so
        # this is safe to auto-qualify. Without an equivalent rule here, every
        # lead for a remote business would silently fall through to
        # qualification.default_outcome ("needs_human" below) forever, with
        # no way for the owner to notice or fix it (no Settings UI edits
        # qualification.rules).
        else [{"field": "service_id", "operator": "exists", "value": True, "outcome": "qualified"}]
    )
    # No zip codes submitted means the business has no fixed service area at all
    # (remote/nationwide/online) -- QualificationService._service_area_status()
    # short-circuits to "inside" for every lead whenever enforce_service_area is
    # false, so the `remote` area below is never actually read for matching; it
    # only exists because the schema requires every service to reference at
    # least one service_area_id with a non-empty `values` array.
    is_remote = not onboarding.service_zip_codes
    escalation_triggers = [
        trigger
        for trigger, enabled in (
            ("high", onboarding.escalate_on_high_urgency),
            ("emergency", onboarding.escalate_on_emergency),
        )
        if enabled
    ]

    return {
        "schema_version": "1.1",
        "business": {
            "id": onboarding.business_id,
            "name": onboarding.business_name,
            "industry": onboarding.industry,
            "description": onboarding.description.strip(),
            "timezone": timezone,
            "currency": "USD",
        },
        "services": _build_services(onboarding.services),
        "service_areas": [
            {
                "id": _SERVICE_AREA_ID,
                "type": "remote" if is_remote else "postal_codes",
                "values": ["everywhere"] if is_remote else list(onboarding.service_zip_codes),
            },
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
                # Not in required_fields above, but QualificationService (see
                # src/engine/qualification_service.py) dynamically adds these two
                # exact keys to missing_fields whenever it can't identify the
                # requested service or the service area from the customer's
                # message — regardless of what's configured as "required". Without
                # a question configured for both, DeterministicQuestionGenerator
                # raises and the customer's chat fails with an unhandled 500 the
                # first time a message doesn't cleanly match a service or zip.
                "service_id": "What kind of service do you need help with?",
                "customer_location": (
                    "Is there anything else about your location we should know?"
                    if is_remote
                    else "What's the ZIP code where you need service?"
                ),
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
            # Separate wording for the one decline the customer can act on.
            # The generic sentence above reads as "we don't do that", so a
            # lead just outside the area never learns that the address was
            # the problem. Zero-config: shipped as a default, not a field the
            # owner has to discover. Optional downstream -- LeadIntakeService
            # falls back to lost_message when it is absent (see
            # _lost_message), so DNA written before 2026-08-25 is unaffected
            # and no migration is required.
            "lost_message_out_of_area": (
                "Sorry — that address is outside the area we currently serve. "
                "If you have another address nearby, send the ZIP code and "
                "we'll check it right away."
            ),
            # Empty by default -- no behavior change for businesses that don't
            # need it (see QualificationService: an empty list here means the
            # reassurance-response feature never activates). An owner fills
            # this in later with their own typical objections and the exact
            # response approved for each; the AI only ever selects and
            # rephrases one of these entries, it never invents a new one.
            "objection_responses": [],
        },
        "booking": {
            "enabled": False,
            "timezone": timezone,
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
            "review_request_message": "Thanks for working with us. If you have a moment, a short review or referral helps other customers find the business.",
            "opening_pitch": compose_opening_pitch(
                onboarding.business_name,
                onboarding.description,
                tuple(service.name for service in onboarding.services),
            ),
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
            # Empty by default -- no behavior change for businesses that don't
            # need one. An owner (or a regulated-industry onboarding path)
            # fills this in via Settings; see compliance_disclaimer in the
            # schema for how it's enforced.
            "compliance_disclaimer": "",
        },
        "chat_widget": {
            "enabled": True,
            "title": f"Chat with {onboarding.business_name}",
            "welcome_message": (
                f"Hi — this is {onboarding.business_name}. "
                "Tell me what's going on and I'll help you from there."
            ),
            "qualified_message": "Thanks — we have what we need. Our team will follow up with next steps.",
            "closed_message": "This conversation is complete. Please reach out again if you need more help.",
            "ai_disclosure_text": "",
        },
        "ai_permissions": {
            "allowed": ["classify_intent", "extract_customer_details", "draft_message"],
            "forbidden": ["issue_refund", "change_price", "capture_payment", "make_legal_commitment"],
            "minimum_confidence": 0.8,
        },
        "human_escalation": {
            "triggers": escalation_triggers,
            "queue": "operations",
            "response_target_minutes": 30,
            "customer_message": "A team member needs to review your request and will follow up shortly.",
        },
        "integrations": {},
    }
