"""Live Business DNA editing for the Settings page.

Every change creates a NEW Business DNA version (see
`BusinessDNARepository.add_version`) -- Business DNA is versioned and
immutable by design, so a Settings save never rewrites history, only what
NEW conversations see from that point on.

Only the fields the Settings page actually edits are touched here --
business name/industry, communication tone, the service list (with each
service's qualification questions), the service-area zip codes, and which
customer-urgency signals (see `Urgency` in src/domain/qualification.py,
consumed by `QualificationService.evaluate`) route a case to a human.
Everything else already configured -- pricing, booking hours, payment, AI
permissions, the qualification-rules engine -- carries over completely
unchanged from the current active version, so a Settings save can never
silently reset configuration made elsewhere (onboarding, or a future
pricing/booking editor).
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator

from src.domain.business_dna_builder import slugify
from src.domain.tenancy import BusinessDNAVersion

from .business_provisioning_service import InvalidBusinessDNAError
from .repositories import UnitOfWork

_SCHEMA_PATH = Path(__file__).parents[2] / "config" / "business_dna.schema.json"
_PRIMARY_AREA_ID = "primary"
_ALL_WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)
_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
# Wide enough to never further restrict business_hours -- booking.allowed_times
# is required non-empty by the schema, so this is the "no extra restriction"
# placeholder when Settings owns business_hours as the single source of truth
# for when a business is open (see DeterministicAvailabilityEngine._intersect_windows).
_UNRESTRICTED_ALLOWED_TIMES = [{"starts": "00:00", "ends": "23:59"}]
# The only two Urgency values (src/domain/qualification.py::Urgency) it makes sense
# to let a business owner opt into escalating on -- QualificationService.evaluate()
# checks `intent.urgency.value in business_dna["human_escalation"]["triggers"]`, and
# "low"/"normal"/"unknown" escalating to a human would defeat the point of automation.
_RECOGNIZED_URGENCY_TRIGGERS = ("high", "emergency")


class BusinessDNANotConfiguredError(RuntimeError):
    """The business has no active Business DNA version yet (shouldn't happen for a
    provisioned business, but the route defends against it anyway)."""


@dataclass(frozen=True, slots=True)
class SettingsServiceInput:
    id: str | None
    name: str
    questions: tuple[str, ...]
    # When True, Settings turns this service fully bookable (fulfillment_type
    # "bookable" + booking_allowed True); when False it resets to the safe
    # "human_review" default. See BusinessDNASettingsService._apply.
    bookable: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("service name must not be empty")


@dataclass(frozen=True, slots=True)
class SettingsUpdate:
    name: str
    industry: str
    tone: str
    services: tuple[SettingsServiceInput, ...]
    service_zip_codes: tuple[str, ...]
    escalate_on_high_urgency: bool
    escalate_on_emergency: bool
    booking_enabled: bool = False
    booking_timezone: str = "UTC"
    # Empty means "leave whatever business_hours is already configured
    # unchanged" -- see _apply. Keys must be from _ALL_WEEKDAYS; a day with no
    # windows (or omitted entirely) means the business is closed that day.
    business_hours: Mapping[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.industry.strip():
            raise ValueError("industry must not be empty")
        if not self.tone.strip():
            raise ValueError("tone must not be empty")
        if not self.services:
            raise ValueError("at least one service is required")
        try:
            ZoneInfo(self.booking_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("booking_timezone is not a recognized timezone") from exc
        for day, windows in self.business_hours.items():
            if day not in _ALL_WEEKDAYS:
                raise ValueError(f"business_hours has an unrecognized day: {day}")
            for opens, closes in windows:
                if not _TIME_PATTERN.match(opens) or not _TIME_PATTERN.match(closes):
                    raise ValueError("business_hours times must use HH:MM (24h)")
                if closes <= opens:
                    raise ValueError("business_hours windows must close after they open")
        # Empty is valid -- it means "no fixed service area" (see _apply, which
        # maps that to a `remote` service area instead of `postal_codes`).


def _load_schema() -> dict:
    with _SCHEMA_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def _deep_copy(value: Any) -> Any:
    """Unfreeze a `BusinessDNAVersion.configuration` into plain, mutable
    dict/list. The stored configuration is recursively frozen into
    MappingProxyType/tuple (see `_freeze` in src/domain/models.py) so it can
    be safely shared -- `dict(value)` alone only unwraps the top level, which
    is exactly the bug fixed in DashboardEventSchema.from_domain; this is the
    same fix applied where we additionally need to *mutate* the result."""
    if isinstance(value, Mapping):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_deep_copy(item) for item in value]
    return value


class BusinessDNASettingsService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._schema = _load_schema()

    def get_active(self, business_id: str) -> BusinessDNAVersion:
        with self._unit_of_work_factory() as unit_of_work:
            version = unit_of_work.business_dna.get_active(business_id)
        if version is None:
            raise BusinessDNANotConfiguredError(f"business {business_id} has no active Business DNA")
        return version

    def update(self, business_id: str, update: SettingsUpdate) -> BusinessDNAVersion:
        submitted_ids = [item.id for item in update.services if item.id]
        if len(submitted_ids) != len(set(submitted_ids)):
            raise InvalidBusinessDNAError("duplicate service id submitted")

        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.business_dna.get_active(business_id)
            if current is None:
                raise BusinessDNANotConfiguredError(f"business {business_id} has no active Business DNA")
            configuration = self._apply(_deep_copy(current.configuration), update)
            try:
                Draft202012Validator(self._schema).validate(configuration)
            except Exception as exc:  # jsonschema.ValidationError, kept generic to avoid a hard import cycle
                raise InvalidBusinessDNAError(str(exc)) from exc
            new_version = unit_of_work.business_dna.add_version(business_id, configuration)
            unit_of_work.commit()
        return new_version

    @staticmethod
    def _apply(config: dict, update: SettingsUpdate) -> dict:
        config["business"]["name"] = update.name
        config["business"]["industry"] = update.industry
        config["communication"]["tone"] = update.tone

        existing_by_id = {service["id"]: service for service in config["services"]}
        used_ids: set[str] = set()
        rebuilt: list[dict] = []
        for item in update.services:
            source = existing_by_id.get(item.id) if item.id else None
            if source is not None:
                service = dict(source)
            else:
                base_id = slugify(item.name)
                candidate = base_id
                suffix = 2
                while candidate in used_ids or candidate in existing_by_id:
                    candidate = f"{base_id}-{suffix}"
                    suffix += 1
                service = {
                    "id": candidate,
                    "name": item.name,
                    "description": item.name,
                    "duration_minutes": 60,
                    "fulfillment_type": "human_review",
                    "pricing": {"model": "custom_quote", "tax_included": False},
                    "service_area_ids": [_PRIMARY_AREA_ID],
                    "intake_keywords": [],
                    "booking_allowed": False,
                    "qualification_questions": [],
                }
            service["name"] = item.name
            service["intake_keywords"] = sorted(
                {*service.get("intake_keywords", []), item.name.strip().casefold()}
            )
            service["qualification_questions"] = [
                {
                    "id": slugify(question, fallback=f"question-{index}"),
                    "prompt": question,
                    "required": True,
                    "disqualifying_answers": [],
                }
                for index, question in enumerate(item.questions, start=1)
            ]
            if item.bookable:
                service["fulfillment_type"] = "bookable"
                service["booking_allowed"] = True
            else:
                service["fulfillment_type"] = "human_review"
                service["booking_allowed"] = False
            used_ids.add(service["id"])
            rebuilt.append(service)
        config["services"] = rebuilt

        areas = config["service_areas"]
        primary = next((area for area in areas if area["id"] == _PRIMARY_AREA_ID), None)
        if primary is None:
            primary = {"id": _PRIMARY_AREA_ID, "type": "postal_codes", "values": []}
            areas = [*areas, primary]
        else:
            primary = dict(primary)
            areas = [primary if area["id"] == _PRIMARY_AREA_ID else area for area in areas]
        # No zip codes submitted means "no fixed service area" (a remote/
        # nationwide business), same convention as onboarding
        # (src/domain/business_dna_builder.py). `values` is required non-empty by
        # the schema even for a remote area, so it gets a placeholder that's
        # never actually read for matching (enforce_service_area below is what
        # actually turns matching off).
        cleaned_zips = list(dict.fromkeys(zip_code.strip() for zip_code in update.service_zip_codes if zip_code.strip()))
        is_remote = not cleaned_zips
        primary["type"] = "remote" if is_remote else "postal_codes"
        primary["values"] = ["everywhere"] if is_remote else cleaned_zips
        config["service_areas"] = areas
        config["qualification"]["enforce_service_area"] = not is_remote
        # Retroactive fix for businesses that switched to remote/Anywhere (or
        # onboarded that way before this rule existed -- see
        # business_dna_builder.build_business_dna for the matching onboarding-time
        # fix): with no rules configured, QualificationService._qualification_rule_outcome
        # falls through to default_outcome ("needs_human"), so a remote business
        # with an empty rules array would otherwise never auto-qualify a single
        # lead. Only fires when rules is genuinely empty -- never overwrites
        # rules an owner already configured some other way.
        if is_remote and not config["qualification"].get("rules"):
            config["qualification"]["rules"] = [
                {"field": "service_id", "operator": "exists", "value": True, "outcome": "qualified"}
            ]

        other_triggers = [
            trigger
            for trigger in config["human_escalation"]["triggers"]
            if trigger not in _RECOGNIZED_URGENCY_TRIGGERS
        ]
        triggers = list(other_triggers)
        if update.escalate_on_high_urgency:
            triggers.append("high")
        if update.escalate_on_emergency:
            triggers.append("emergency")
        config["human_escalation"]["triggers"] = triggers

        # Settings is the single owner of business_hours + booking.timezone/
        # enabled once an owner has touched this tab. allowed_days/allowed_times
        # are widened to "no extra restriction" so business_hours alone decides
        # which days/windows are actually open (see DeterministicAvailabilityEngine
        # in src/engine/commercial.py) -- everything else in booking (buffers,
        # capacity, notice windows, cancellation policy, ...) carries over
        # unchanged from whatever onboarding or a prior save left configured.
        if update.business_hours:
            config["business_hours"] = {
                day: [{"opens": opens, "closes": closes} for opens, closes in windows]
                for day, windows in update.business_hours.items()
                if windows
            }
        booking = dict(config.get("booking", {}))
        booking["enabled"] = update.booking_enabled
        booking["timezone"] = update.booking_timezone
        booking["allowed_days"] = list(_ALL_WEEKDAYS)
        booking["allowed_times"] = list(_UNRESTRICTED_ALLOWED_TIMES)
        config["booking"] = booking
        config["business"]["timezone"] = update.booking_timezone

        return config
