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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.domain.business_dna_builder import slugify
from src.domain.tenancy import BusinessDNAVersion

from .business_provisioning_service import InvalidBusinessDNAError
from .repositories import UnitOfWork

_SCHEMA_PATH = Path(__file__).parents[2] / "config" / "business_dna.schema.json"
_PRIMARY_AREA_ID = "primary"
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

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.industry.strip():
            raise ValueError("industry must not be empty")
        if not self.tone.strip():
            raise ValueError("tone must not be empty")
        if not self.services:
            raise ValueError("at least one service is required")
        if not self.service_zip_codes:
            raise ValueError("at least one service zip code is required")


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
        primary["type"] = "postal_codes"
        primary["values"] = list(
            dict.fromkeys(zip_code.strip() for zip_code in update.service_zip_codes if zip_code.strip())
        )
        config["service_areas"] = areas

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

        return config
