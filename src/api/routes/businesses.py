"""Safe tenant metadata endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.domain.tenancy import Business

from ..dependencies import resolve_business
from ..schemas import BusinessResponse, ErrorResponse


router = APIRouter(prefix="/api/v1/businesses", tags=["businesses"])


@router.get(
    "/{business_id}",
    response_model=BusinessResponse,
    responses={404: {"model": ErrorResponse, "description": "Business not found"}},
    summary="Get safe business metadata",
)
def get_business(
    business: Annotated[Business, Depends(resolve_business)],
) -> BusinessResponse:
    return BusinessResponse.from_domain(business)
