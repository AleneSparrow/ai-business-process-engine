"""Pydantic request and response contracts for API v1."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.domain.qualification import LeadIntakeResult
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.engine.lead_intake import LeadIntakeService
from src.domain.conversations import ConversationStatus, MessageDirection, MessageRole
from src.persistence.conversation_service import PublicConversation


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


def validation_issues(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "location": tuple(error.get("loc", ())),
            "message": str(error.get("msg", "Invalid value")),
            "type": str(error.get("type", "value_error")),
        }
        for error in errors
    ]
