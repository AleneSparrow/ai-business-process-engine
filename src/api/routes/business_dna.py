"""Live Business DNA read/edit for the Settings page.

See `src/persistence/business_dna_settings_service.py` for exactly what a
save touches vs carries over unchanged from the current active version.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.domain.auth import StaffUser
from src.persistence.business_dna_settings_service import (
    BusinessDNANotConfiguredError,
    BusinessDNASettingsService,
    SettingsServiceInput,
    SettingsUpdate,
)

from ..dependencies import BusinessIdPath, get_business_dna_settings_service, require_own_business
from ..errors import RequestDataError, ResourceNotFoundError
from ..schemas import BusinessDNASettingsResponse, BusinessDNASettingsUpdateRequest

router = APIRouter(prefix="/api/v1/businesses/{business_id}", tags=["business dna"])


def _not_configured() -> ResourceNotFoundError:
    return ResourceNotFoundError(
        "business_dna_not_configured", "This business has no active configuration"
    )


@router.get("/dna", response_model=BusinessDNASettingsResponse)
def get_settings(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    service: Annotated[BusinessDNASettingsService, Depends(get_business_dna_settings_service)],
) -> BusinessDNASettingsResponse:
    try:
        dna = service.get_active(business_id)
    except BusinessDNANotConfiguredError as exc:
        raise _not_configured() from exc
    return BusinessDNASettingsResponse.from_domain(dna)


@router.put("/dna", response_model=BusinessDNASettingsResponse)
def update_settings(
    business_id: BusinessIdPath,
    body: BusinessDNASettingsUpdateRequest,
    user: Annotated[StaffUser, Depends(require_own_business)],
    service: Annotated[BusinessDNASettingsService, Depends(get_business_dna_settings_service)],
) -> BusinessDNASettingsResponse:
    try:
        update = SettingsUpdate(
            name=body.name,
            industry=body.industry,
            tone=body.tone,
            services=tuple(
                SettingsServiceInput(id=item.id, name=item.name, questions=item.questions, bookable=item.bookable)
                for item in body.services
            ),
            service_zip_codes=body.service_zip_codes,
            escalate_on_high_urgency=body.escalate_on_high_urgency,
            escalate_on_emergency=body.escalate_on_emergency,
            booking_enabled=body.booking_enabled,
            booking_timezone=body.booking_timezone,
            business_hours={
                day: tuple((window.opens, window.closes) for window in windows)
                for day, windows in body.business_hours.items()
            },
        )
        dna = service.update(business_id, update)
    except BusinessDNANotConfiguredError as exc:
        raise _not_configured() from exc
    except ValueError as exc:
        raise RequestDataError(str(exc)) from exc
    return BusinessDNASettingsResponse.from_domain(dna)
