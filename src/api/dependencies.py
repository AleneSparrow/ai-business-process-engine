"""Request-scoped dependency wiring for database-backed services."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy import Engine

from src.config import Settings
from src.domain.tenancy import Business
from src.engine.intent_extractor import IntentExtractor
from src.engine.customer_response_generator import CustomerResponseGenerator
from src.engine.question_generator import QuestionGenerator
from src.persistence.lead_intake import PersistentLeadIntakeService
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork

from .errors import ResourceNotFoundError


BusinessIdPath = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
]
UnitOfWorkFactory = Callable[[], SQLAlchemyUnitOfWork]


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    settings: Settings
    engine: Engine
    unit_of_work_factory: UnitOfWorkFactory
    intent_extractor: IntentExtractor
    question_generator: QuestionGenerator
    customer_response_generator: CustomerResponseGenerator
    ai_provider_name: str
    ai_model_name: str


def get_container(request: Request) -> ApplicationContainer:
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, ApplicationContainer):
        raise RuntimeError("application dependencies are not initialized")
    return container


def get_unit_of_work_factory(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> UnitOfWorkFactory:
    return container.unit_of_work_factory


def get_intake_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> PersistentLeadIntakeService:
    return PersistentLeadIntakeService(
        container.unit_of_work_factory,
        container.intent_extractor,
        container.question_generator,
        customer_response_generator=container.customer_response_generator,
    )


def resolve_business(
    request: Request,
    business_id: BusinessIdPath,
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> Business:
    request.state.business_id = business_id
    with unit_of_work_factory() as unit_of_work:
        business = unit_of_work.businesses.get(business_id)
    if business is None:
        raise ResourceNotFoundError("business_not_found", "Business was not found")
    return business
