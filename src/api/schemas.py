"""Pydantic request and response contracts for API v1."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.domain.models import Lead, ProcessCase, ProcessEvent
from src.domain.qualification import LeadIntakeResult
from src.domain.states import ProcessState
from src.domain.tenancy import Business, BusinessDNAVersion
from src.engine.lead_intake import LeadIntakeService
from src.domain.conversations import Conversation, ConversationStatus, MessageDirection, MessageRole
from src.domain.commercial import BookingStatus, PaymentStatus, PaymentType, QuoteStatus
from src.persistence.conversation_service import PublicCommercialSnapshot, PublicConversation


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IncomingMessageRequest(ApiModel):
    channel: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")]
    external_message_id: Annotated[str, Field(min_length=1, max_length=255)]
    message: Annotated[str, Field(min_length=1, max_length=10_000)]
    timestamp: AwareDatetime
    customer_name: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    phone: Annotated[str | None, Field(min_length=1, max_length=64)] = None
    email: Annotated[str | None, Field(min_length=1, max_length=320)] = None
    case_id: Annotated[str | None, Field(min_length=1, max_length=128)] = None

    @field_validator("channel")
    @classmethod
    def normalize_channel(cls, value: str) -> str:
        return value.casefold()

    @field_validator("external_message_id")
    @classmethod
    def validate_external_message_id(cls, value: str) -> str:
        if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("external_message_id must not contain whitespace or control characters")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(character not in "+-(). 0123456789" for character in value):
            raise ValueError("phone contains unsupported characters")
        LeadIntakeService._normalize_phone(value)
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return LeadIntakeService._normalize_email(value)


class CustomerResponseSchema(ApiModel):
    message_text: str
    channel: str
    reason: str
    related_case_id: str
    requires_human: bool


class QualificationSummarySchema(ApiModel):
    qualified: bool
    reasons: tuple[str, ...]
    missing_fields: tuple[str, ...]
    unanswered_questions: tuple[str, ...]
    confidence: float
    recommended_next_state: ProcessState
    requires_human: bool
    booking_allowed: bool
    service_id: str | None


class LeadIntakeResponse(ApiModel):
    business_id: str
    case_id: str
    lead_id: str
    current_state: ProcessState
    duplicate: bool
    case_created: bool
    customer_response: CustomerResponseSchema | None
    requires_human: bool
    qualification: QualificationSummarySchema

    @classmethod
    def from_result(cls, business_id: str, result: LeadIntakeResult) -> "LeadIntakeResponse":
        response = result.response
        qualification = result.qualification
        return cls(
            business_id=business_id,
            case_id=result.case_id,
            lead_id=result.lead_id,
            current_state=result.current_state,
            duplicate=result.duplicate,
            case_created=result.case_created,
            customer_response=None if response is None else CustomerResponseSchema(
                message_text=response.message_text,
                channel=response.channel,
                reason=response.reason,
                related_case_id=response.related_case_id,
                requires_human=response.requires_human,
            ),
            requires_human=qualification.requires_human or bool(response and response.requires_human),
            qualification=QualificationSummarySchema(
                qualified=qualification.qualified,
                reasons=qualification.reasons,
                missing_fields=qualification.missing_fields,
                unanswered_questions=qualification.unanswered_questions,
                confidence=qualification.confidence,
                recommended_next_state=qualification.recommended_next_state,
                requires_human=qualification.requires_human,
                booking_allowed=qualification.booking_allowed,
                service_id=qualification.service_id,
            ),
        )


class BusinessResponse(ApiModel):
    business_id: str
    name: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, business: Business) -> "BusinessResponse":
        return cls(
            business_id=business.business_id,
            name=business.name,
            created_at=business.created_at,
            updated_at=business.updated_at,
        )


# --- CRM webhook: optional outbound sync (e.g. Clio) on QUALIFIED/WON cases --
# The URL itself is never returned by the API -- it's effectively a bearer
# secret (Zapier/Make-style catch hooks embed a token in the path).


class CrmWebhookStatusResponse(ApiModel):
    configured: bool


class CrmWebhookConfigureRequest(ApiModel):
    webhook_url: str = Field(min_length=1, max_length=2048)


class SmsStatusResponse(ApiModel):
    configured: bool
    phone_number: str | None = None


# --- Billing: self-serve Lemon Squeezy subscription for the business's own Flywheel account --


class BillingStatusResponse(ApiModel):
    plan: Literal["starter", "pro"] | None
    subscription_status: str
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    has_billing_access: bool

    @classmethod
    def from_domain(cls, business: Business) -> "BillingStatusResponse":
        return cls(
            plan=business.plan,
            subscription_status=business.subscription_status,
            trial_ends_at=business.trial_ends_at,
            current_period_end=business.current_period_end,
            has_billing_access=business.has_billing_access,
        )


class CheckoutSessionRequest(ApiModel):
    plan: Literal["starter", "pro"]


class CheckoutSessionResponse(ApiModel):
    checkout_url: str


class PortalSessionResponse(ApiModel):
    portal_url: str


class HealthResponse(ApiModel):
    status: str


class ReadinessResponse(ApiModel):
    status: str
    dependencies: dict[str, str]


class ValidationIssue(ApiModel):
    location: tuple[str | int, ...]
    message: str
    type: str


class ErrorDetail(ApiModel):
    code: str
    message: str
    request_id: str
    details: list[ValidationIssue] | None = None


class ErrorResponse(ApiModel):
    error: ErrorDetail


class PublicConversationCreateRequest(ApiModel):
    message: Annotated[str | None, Field(min_length=1, max_length=10_000)] = None
    external_message_id: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    conversation_token: Annotated[
        str | None,
        Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$"),
    ] = None

    @model_validator(mode="after")
    def require_complete_first_message(self) -> "PublicConversationCreateRequest":
        if (self.message is None) != (self.external_message_id is None):
            raise ValueError("message and external_message_id must be supplied together")
        return self

    @field_validator("external_message_id")
    @classmethod
    def validate_external_message_id(cls, value: str | None) -> str | None:
        if value is not None and any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        ):
            raise ValueError("external_message_id must not contain whitespace or control characters")
        return value


class PublicConversationMessageRequest(ApiModel):
    message: Annotated[str, Field(min_length=1, max_length=10_000)]
    external_message_id: Annotated[str, Field(min_length=1, max_length=255)]

    @field_validator("external_message_id")
    @classmethod
    def validate_external_message_id(cls, value: str) -> str:
        if any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        ):
            raise ValueError("external_message_id must not contain whitespace or control characters")
        return value


class PublicConversationMessageSchema(ApiModel):
    direction: MessageDirection
    role: MessageRole
    text: str
    created_at: datetime


class PublicConversationResponse(ApiModel):
    conversation_token: str
    status: ConversationStatus
    current_state: ProcessState | None
    requires_human: bool
    duplicate: bool
    messages: tuple[PublicConversationMessageSchema, ...]

    @classmethod
    def from_domain(cls, conversation: PublicConversation) -> "PublicConversationResponse":
        return cls(
            conversation_token=conversation.conversation_token,
            status=conversation.status,
            current_state=conversation.current_state,
            requires_human=conversation.requires_human,
            duplicate=conversation.duplicate,
            messages=tuple(
                PublicConversationMessageSchema(
                    direction=message.direction,
                    role=message.role,
                    text=message.text,
                    created_at=message.created_at,
                )
                for message in conversation.messages
            ),
        )


class PublicChatConfigResponse(ApiModel):
    enabled: bool
    business_name: str
    chat_title: str
    welcome_message: str
    language: str
    ai_disclosure_text: str


class PublicBookingSchema(ApiModel):
    booking_id: str
    service_id: str
    status: BookingStatus
    start_at: datetime
    end_at: datetime
    timezone: str


class PublicQuoteSchema(ApiModel):
    quote_id: str
    service_id: str
    status: QuoteStatus
    currency: str
    total: Decimal
    valid_until: datetime


class PublicPaymentRequestSchema(ApiModel):
    payment_request_id: str
    status: PaymentStatus
    payment_type: PaymentType
    amount: Decimal
    currency: str
    expires_at: datetime


class PublicCommercialResponse(ApiModel):
    current_state: ProcessState | None
    booking: PublicBookingSchema | None
    quote: PublicQuoteSchema | None
    payment_request: PublicPaymentRequestSchema | None

    @classmethod
    def from_domain(cls, value: PublicCommercialSnapshot) -> "PublicCommercialResponse":
        return cls(
            current_state=value.current_state,
            booking=(
                PublicBookingSchema(
                    booking_id=value.booking.booking_id,
                    service_id=value.booking.service_id,
                    status=value.booking.status,
                    start_at=value.booking.start_at,
                    end_at=value.booking.end_at,
                    timezone=value.booking.timezone,
                )
                if value.booking is not None
                else None
            ),
            quote=(
                PublicQuoteSchema(
                    quote_id=value.quote.quote_id,
                    service_id=value.quote.service_id,
                    status=value.quote.status,
                    currency=value.quote.currency,
                    total=value.quote.total,
                    valid_until=value.quote.valid_until,
                )
                if value.quote is not None
                else None
            ),
            payment_request=(
                PublicPaymentRequestSchema(
                    payment_request_id=value.payment_request.payment_request_id,
                    status=value.payment_request.status,
                    payment_type=value.payment_request.payment_type,
                    amount=value.payment_request.amount,
                    currency=value.payment_request.currency,
                    expires_at=value.payment_request.expires_at,
                )
                if value.payment_request is not None
                else None
            ),
        )


def validation_issues(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "location": tuple(error.get("loc", ())),
            "message": str(error.get("msg", "Invalid value")),
            "type": str(error.get("type", "value_error")),
        }
        for error in errors
    ]


# --- Staff authentication -----------------------------------------------------------------


def _validate_email_shape(value: str) -> str:
    stripped = value.strip()
    if "@" not in stripped or " " in stripped or stripped.startswith("@") or stripped.endswith("@"):
        raise ValueError("email is not a valid address")
    return stripped


class SignupRequest(ApiModel):
    email: Annotated[str, Field(min_length=3, max_length=320)]
    password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email_shape(value)


class LoginRequest(ApiModel):
    email: Annotated[str, Field(min_length=3, max_length=320)]
    password: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email_shape(value)


class StaffUserResponse(ApiModel):
    user_id: str
    email: str
    business_id: str | None


class SessionResponse(ApiModel):
    token: str
    expires_in_hours: int
    user: StaffUserResponse


# --- Self-serve business onboarding -------------------------------------------------------


class OnboardingServiceRequest(ApiModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    questions: Annotated[list[Annotated[str, Field(min_length=1, max_length=300)]], Field(max_length=20)] = []


class OnboardingRequest(ApiModel):
    business_name: Annotated[str, Field(min_length=1, max_length=255)]
    # No longer defaulted to a specific vertical -- the wizard now requires the
    # owner to type their own industry (any business, not just home services).
    industry: Annotated[str, Field(min_length=1, max_length=120)]
    tone: Annotated[str, Field(min_length=1, max_length=60)] = "Friendly & direct"
    services: Annotated[list[OnboardingServiceRequest], Field(min_length=1, max_length=50)]
    # Empty means "no fixed service area" (a remote/nationwide business) -- see
    # build_business_dna, which maps that to a `remote` service area instead of
    # `postal_codes`. Only required when enforce_service_area is true.
    service_zip_codes: Annotated[list[Annotated[str, Field(min_length=1, max_length=20)]], Field(max_length=500)] = []
    enforce_service_area: bool = True
    # Real Urgency-based triggers (see QualificationService.evaluate) -- replaces
    # the old onboarding wizard's three checkboxes, which were never actually
    # sent to the backend at all and had no effect on the created business.
    escalate_on_high_urgency: bool = True
    escalate_on_emergency: bool = True

    @field_validator("service_zip_codes")
    @classmethod
    def validate_zip_codes(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        # De-duplicate while preserving order.
        seen: set[str] = set()
        unique = []
        for item in cleaned:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    @model_validator(mode="after")
    def require_zip_codes_when_area_is_enforced(self) -> "OnboardingRequest":
        if self.enforce_service_area and not self.service_zip_codes:
            raise ValueError("at least one service zip code is required when a service area is enforced")
        return self


class BusinessCreatedResponse(ApiModel):
    business_id: str
    name: str
    widget_snippet: str

    @classmethod
    def from_domain(cls, business: Business, *, api_base: str | None = None) -> "BusinessCreatedResponse":
        base_attr = f' data-api-base="{api_base}"' if api_base else ""
        snippet = (
            f'<script src="/widget/widget.js" data-business-id="{business.business_id}"{base_attr}></script>'
        )
        return cls(business_id=business.business_id, name=business.name, widget_snippet=snippet)


# --- Staff dashboard: real cases, conversations, and audit trail --------------------------


class DashboardLeadSchema(ApiModel):
    lead_id: str
    name: str | None
    email: str | None
    phone: str | None

    @classmethod
    def from_domain(cls, lead: Lead) -> "DashboardLeadSchema":
        return cls(lead_id=lead.lead_id, name=lead.name, email=lead.email, phone=lead.phone)


class DashboardCaseSummarySchema(ApiModel):
    case_id: str
    lead: DashboardLeadSchema
    current_state: ProcessState
    created_at: datetime
    updated_at: datetime
    event_count: int
    latest_event_type: str | None

    @classmethod
    def from_domain(cls, case: ProcessCase) -> "DashboardCaseSummarySchema":
        latest = case.event_history[-1] if case.event_history else None
        return cls(
            case_id=case.case_id,
            lead=DashboardLeadSchema.from_domain(case.lead),
            current_state=case.current_state,
            created_at=case.created_at,
            updated_at=case.updated_at,
            event_count=len(case.event_history),
            latest_event_type=str(latest.event_type) if latest else None,
        )


class DashboardCaseListResponse(ApiModel):
    cases: tuple[DashboardCaseSummarySchema, ...]


def _jsonable(value: Any) -> Any:
    """Recursively unwrap the immutable containers `ProcessEvent.payload` is
    frozen into (see `_freeze` in src/domain/models.py). `dict(event.payload)`
    alone only unwraps the top level -- any nested dict/list/set value stays a
    MappingProxyType/frozenset/tuple, and pydantic-core's JSON serializer
    can't encode a MappingProxyType, so any event with a nested payload value
    (e.g. DECISION_RECORDED's "metadata") 500s the dashboard case-detail
    endpoint without this."""
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set | frozenset):
        return [_jsonable(item) for item in value]
    return value


class DashboardEventSchema(ApiModel):
    event_id: str
    event_type: str
    source: str
    occurred_at: datetime
    payload: dict[str, Any]

    @classmethod
    def from_domain(cls, event: ProcessEvent) -> "DashboardEventSchema":
        return cls(
            event_id=event.event_id,
            event_type=str(event.event_type),
            source=event.source,
            occurred_at=event.occurred_at,
            payload=_jsonable(event.payload),
        )


class DashboardCaseDetailResponse(ApiModel):
    case_id: str
    lead: DashboardLeadSchema
    current_state: ProcessState
    created_at: datetime
    updated_at: datetime
    events: tuple[DashboardEventSchema, ...]

    @classmethod
    def from_domain(cls, case: ProcessCase) -> "DashboardCaseDetailResponse":
        return cls(
            case_id=case.case_id,
            lead=DashboardLeadSchema.from_domain(case.lead),
            current_state=case.current_state,
            created_at=case.created_at,
            updated_at=case.updated_at,
            events=tuple(DashboardEventSchema.from_domain(event) for event in case.event_history),
        )


class DashboardConversationSchema(ApiModel):
    conversation_id: str
    case_id: str | None
    lead_id: str | None
    lead_name: str | None
    case_state: ProcessState | None
    channel: str
    status: ConversationStatus
    created_at: datetime
    last_activity_at: datetime

    @classmethod
    def from_domain(
        cls,
        conversation: Conversation,
        *,
        lead_name: str | None = None,
        case_state: ProcessState | None = None,
    ) -> "DashboardConversationSchema":
        return cls(
            conversation_id=conversation.conversation_id,
            case_id=conversation.case_id,
            lead_id=conversation.lead_id,
            lead_name=lead_name,
            case_state=case_state,
            channel=conversation.channel,
            status=conversation.status,
            created_at=conversation.created_at,
            last_activity_at=conversation.last_activity_at,
        )


class DashboardConversationListResponse(ApiModel):
    conversations: tuple[DashboardConversationSchema, ...]


class DashboardMessageSchema(ApiModel):
    message_id: str
    direction: MessageDirection
    role: MessageRole
    text: str
    created_at: datetime


class DashboardConversationDetailResponse(ApiModel):
    conversation: DashboardConversationSchema
    messages: tuple[DashboardMessageSchema, ...]


class StaffReplyRequest(ApiModel):
    message: Annotated[str, Field(min_length=1, max_length=10_000)]


class StaffActionResponse(ApiModel):
    conversation: DashboardConversationSchema
    case: DashboardCaseSummarySchema | None


class BusinessDNAServiceSchema(ApiModel):
    id: str
    name: str
    questions: tuple[str, ...]

    @classmethod
    def from_domain(cls, service: Mapping[str, Any]) -> "BusinessDNAServiceSchema":
        return cls(
            id=str(service["id"]),
            name=str(service["name"]),
            questions=tuple(str(q["prompt"]) for q in service.get("qualification_questions", [])),
        )


class BusinessDNASettingsResponse(ApiModel):
    version: int
    updated_at: datetime
    name: str
    industry: str
    tone: str
    services: tuple[BusinessDNAServiceSchema, ...]
    service_zip_codes: tuple[str, ...]
    escalate_on_high_urgency: bool
    escalate_on_emergency: bool

    @classmethod
    def from_domain(cls, dna: BusinessDNAVersion) -> "BusinessDNASettingsResponse":
        config = dna.configuration
        primary_area = next(
            (area for area in config["service_areas"] if area["id"] == "primary"),
            None,
        )
        # A `remote` area's `values` is a placeholder (["everywhere"]), never real
        # zip codes -- report an empty list rather than leak that placeholder into
        # the UI as if it were a configured zip code. Settings.tsx treats an empty
        # list as "no fixed area" (see AreaOption / areaMode), matching how the
        # onboarding wizard represents the same choice.
        zips = (
            tuple(str(value) for value in primary_area["values"])
            if primary_area is not None and primary_area["type"] == "postal_codes"
            else ()
        )
        triggers = set(config["human_escalation"]["triggers"])
        return cls(
            version=dna.version,
            updated_at=dna.created_at,
            name=str(config["business"]["name"]),
            industry=str(config["business"]["industry"]),
            tone=str(config["communication"]["tone"]),
            services=tuple(BusinessDNAServiceSchema.from_domain(service) for service in config["services"]),
            service_zip_codes=zips,
            escalate_on_high_urgency="high" in triggers,
            escalate_on_emergency="emergency" in triggers,
        )


class BusinessDNAServiceUpdateSchema(ApiModel):
    id: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    name: Annotated[str, Field(min_length=1, max_length=200)]
    questions: Annotated[tuple[Annotated[str, Field(min_length=1, max_length=500)], ...], Field(max_length=20)] = ()


class BusinessDNASettingsUpdateRequest(ApiModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    industry: Annotated[str, Field(min_length=1, max_length=200)]
    tone: Annotated[str, Field(min_length=1, max_length=500)]
    services: Annotated[tuple[BusinessDNAServiceUpdateSchema, ...], Field(min_length=1, max_length=50)]
    # Empty means "no fixed service area" (a remote/nationwide business) -- see
    # BusinessDNASettingsService._apply, which maps that to a `remote` service
    # area and turns off service-area enforcement, same convention as onboarding.
    service_zip_codes: Annotated[
        tuple[Annotated[str, Field(min_length=1, max_length=32)], ...], Field(max_length=500)
    ] = ()
    escalate_on_high_urgency: bool
    escalate_on_emergency: bool
