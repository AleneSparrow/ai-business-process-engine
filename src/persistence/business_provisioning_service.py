"""Self-serve business creation from the simplified onboarding shape.

Turns the wizard's onboarding payload into a schema-valid Business DNA using
`build_business_dna`, validates it against the packaged JSON Schema before
anything is persisted, creates the tenant and its first Business DNA version,
and links the authenticated account to that one business. Everything commits
or rolls back together — a schema validation failure leaves nothing behind.
"""

import json
import re
from collections.abc import Callable
from pathlib import Path

from jsonschema import Draft202012Validator

from src.domain.auth import StaffUser
from src.domain.business_dna_builder import OnboardingInput, build_business_dna, slugify
from src.domain.models import utc_now
from src.domain.tenancy import Business

from .repositories import UnitOfWork

_SCHEMA_PATH = Path(__file__).parents[2] / "config" / "business_dna.schema.json"
_BUSINESS_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class BusinessProvisioningError(RuntimeError):
    pass


class BusinessIdTakenError(BusinessProvisioningError):
    pass


class InvalidBusinessDNAError(BusinessProvisioningError):
    """Raised only if the generated configuration fails schema validation — a builder bug,
    never something a well-formed onboarding submission alone can trigger."""


def _load_schema() -> dict:
    with _SCHEMA_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def business_id_from_name(name: str) -> str:
    slug = slugify(name, fallback="business")
    return slug if _BUSINESS_ID_PATTERN.match(slug) else "business"


class BusinessProvisioningService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._schema = _load_schema()

    def create_business(self, owner: StaffUser, onboarding: OnboardingInput) -> Business:
        """One account may own any number of businesses -- `owner.with_business`
        links this new one in addition to any the account already has, and
        makes it the account's active business."""
        configuration = build_business_dna(onboarding)
        try:
            Draft202012Validator(self._schema).validate(configuration)
        except Exception as exc:  # jsonschema.ValidationError, kept generic to avoid a hard import cycle
            raise InvalidBusinessDNAError(str(exc)) from exc

        now = utc_now()
        business = Business(onboarding.business_id, onboarding.business_name, now, now)
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.businesses.get(onboarding.business_id) is not None:
                raise BusinessIdTakenError("A business with this identifier already exists")
            unit_of_work.businesses.add(business)
            unit_of_work.business_dna.add_version(onboarding.business_id, configuration)
            linked_owner = owner.with_business(onboarding.business_id)
            unit_of_work.staff_users.save(linked_owner)
            unit_of_work.commit()
        return business
