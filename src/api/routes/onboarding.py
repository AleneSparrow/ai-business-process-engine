"""Self-serve business creation from the onboarding wizard's simplified shape."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.domain.auth import StaffUser
from src.domain.business_dna_builder import OnboardingInput, OnboardingService
from src.persistence.business_provisioning_service import (
    BusinessProvisioningService,
    business_id_from_name,
)
from ..dependencies import (
    UnitOfWorkFactory,
    get_business_provisioning_service,
    get_current_staff_user,
    get_unit_of_work_factory,
    resolve_public_api_base,
)
from ..schemas import BusinessCreatedResponse, OnboardingRequest, OwnedBusinessResponse


router = APIRouter(prefix="/api/v1/businesses", tags=["businesses"])


@router.get("", response_model=list[OwnedBusinessResponse])
def list_my_businesses(
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> list[OwnedBusinessResponse]:
    """Every business the authenticated account is linked to -- powers the
    dashboard's business switcher and "you already have N businesses" UX."""
    with unit_of_work_factory() as unit_of_work:
        businesses = [unit_of_work.businesses.get(business_id) for business_id in user.business_ids]
    return [
        OwnedBusinessResponse(business_id=business.business_id, name=business.name)
        for business in businesses
        if business is not None
    ]


@router.post("", response_model=BusinessCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_business(
    body: OnboardingRequest,
    api_base: Annotated[str, Depends(resolve_public_api_base)],
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
    provisioning_service: Annotated[BusinessProvisioningService, Depends(get_business_provisioning_service)],
) -> BusinessCreatedResponse:
    onboarding = OnboardingInput(
        business_id=business_id_from_name(body.business_name),
        business_name=body.business_name,
        industry=body.industry,
        tone=body.tone,
        services=tuple(
            OnboardingService(service.name, tuple(service.questions)) for service in body.services
        ),
        service_zip_codes=tuple(body.service_zip_codes),
        enforce_service_area=body.enforce_service_area,
        escalate_on_high_urgency=body.escalate_on_high_urgency,
        escalate_on_emergency=body.escalate_on_emergency,
    )
    business = provisioning_service.create_business(user, onboarding)
    return BusinessCreatedResponse.from_domain(business, api_base=api_base)
