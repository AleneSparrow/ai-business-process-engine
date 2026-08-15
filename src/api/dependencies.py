"""Request-scoped dependency wiring for database-backed services."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Path, Request
from sqlalchemy import Engine

from src.config import Settings
from src.domain.auth import StaffUser
from src.domain.tenancy import Business
from src.engine.intent_extractor import IntentExtractor
from src.engine.customer_response_generator import CustomerResponseGenerator
from src.engine.question_generator import QuestionGenerator
from src.persistence.auth_service import AuthService, SessionInvalidError
from src.persistence.billing_service import BillingService
from src.persistence.business_provisioning_service import BusinessProvisioningService
from src.persistence.lead_intake import PersistentLeadIntakeService
from src.persistence.conversation_service import ConversationService
from src.persistence.business_dna_settings_service import BusinessDNASettingsService
from src.persistence.crm_webhook_service import CrmWebhookService
from src.persistence.sms_service import SmsService
from src.persistence.staff_action_service import StaffActionService
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork

from .errors import ForbiddenError, PaymentRequiredError, ResourceNotFoundError, UnauthorizedError
from .rate_limit import RateLimiter


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
    public_chat_rate_limiter: RateLimiter


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


def get_conversation_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> ConversationService:
    return ConversationService(
        container.unit_of_work_factory,
        container.intent_extractor,
        container.question_generator,
        container.customer_response_generator,
        token_ttl_hours=container.settings.public_conversation_token_ttl_hours,
    )


def get_public_chat_rate_limiter(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> RateLimiter:
    return container.public_chat_rate_limiter


def get_auth_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> AuthService:
    return AuthService(container.unit_of_work_factory)


def get_business_provisioning_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> BusinessProvisioningService:
    return BusinessProvisioningService(container.unit_of_work_factory)


def get_staff_action_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> StaffActionService:
    return StaffActionService(container.unit_of_work_factory)


def get_business_dna_settings_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> BusinessDNASettingsService:
    return BusinessDNASettingsService(container.unit_of_work_factory)


def get_crm_webhook_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> CrmWebhookService:
    return CrmWebhookService(container.unit_of_work_factory)


def get_sms_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> SmsService:
    return SmsService(
        container.unit_of_work_factory,
        account_sid=container.settings.twilio_account_sid,
        auth_token=container.settings.twilio_auth_token,
        public_api_base_url=container.settings.public_api_base_url,
    )


def get_billing_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> BillingService:
    return BillingService(container.unit_of_work_factory, container.settings)


def get_current_staff_user(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> StaffUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise UnauthorizedError()
    try:
        return auth_service.authenticate(token)
    except SessionInvalidError as exc:
        raise UnauthorizedError() from exc


def require_business_owner(
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
) -> StaffUser:
    if user.business_id is None:
        raise ForbiddenError("This account has not created a business yet")
    return user


def require_own_business(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(get_current_staff_user)],
) -> StaffUser:
    """Staff-facing dashboard endpoints: the caller may only see their own tenant."""
    if user.business_id != business_id:
        raise ForbiddenError("Not permitted for this business")
    return user


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


def require_active_subscription(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> StaffUser:
    """Gates the staff dashboard (cases/conversations -- the product's actual
    delivered value) on the business having billing access (see
    `Business.has_billing_access`). Deliberately NOT applied to Settings/Business
    DNA (the owner needs to reach billing to fix a lapsed subscription) or to
    public lead-intake/widget routes (a payment problem on Flywheel's side
    shouldn't immediately break the automation a business's own customers are
    already relying on)."""
    with unit_of_work_factory() as unit_of_work:
        business = unit_of_work.businesses.get(business_id)
    if business is None:
        raise ResourceNotFoundError("business_not_found", "Business was not found")
    if not business.has_billing_access:
        raise PaymentRequiredError()
    return user
