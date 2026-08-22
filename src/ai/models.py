"""Typed requests, outputs, and safe audit metadata for AI providers."""

from dataclasses import dataclass, replace
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from src.domain.qualification import CustomerTone, Urgency


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class StrictAIModel(BaseModel):
    """Base for provider responses; unknown fields are always rejected."""

    model_config = ConfigDict(extra="forbid")


class QualificationAnswerOutput(StrictAIModel):
    question_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "A short phrase copied VERBATIM from the customer's own message -- "
            "never a paraphrase, summary, or reordering of their words."
        ),
    )


class IntentOutput(StrictAIModel):
    service_id: str | None = Field(
        max_length=128,
        description=(
            "Set only when the request matches a service listed in BUSINESS_CONTEXT.services. "
            "Null whenever unsupported_service is true."
        ),
    )
    unsupported_service: bool = Field(
        description="True only when the request matches no listed service. Mutually exclusive with service_id."
    )
    unsupported_service_name: str | None = Field(
        max_length=200,
        description=(
            "Set only when unsupported_service is true, to a short VERBATIM phrase copied from the "
            "customer's own words. Null whenever service_id is set."
        ),
    )
    service_evidence: str | None = Field(
        max_length=300,
        description=(
            "The customer's OWN words that justify the service_id you chose -- a short phrase "
            "copied VERBATIM from the current customer message, never a paraphrase and never the "
            "service's own name unless the customer actually used it. It does not need to look "
            "like the service name: for a business whose BUSINESS_CONTEXT describes it as a "
            "family law practice, a customer saying 'I need help with my divorce' justifies a "
            "'Consultation' service with service_evidence='help with my divorce'. Set this "
            "whenever service_id is chosen from the current message. Null only when service_id "
            "is null, or when the service was already established earlier in "
            "CONVERSATION_CONTEXT and the current message does not restate it."
        ),
    )
    urgency: Urgency
    customer_location: str | None = Field(max_length=500)
    preferred_time: str | None = Field(max_length=500)
    notes: str | None = Field(max_length=500)
    customer_name: str | None = Field(max_length=255)
    phone: str | None = Field(max_length=64)
    email: str | None = Field(max_length=320)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human: bool
    qualification_answers: list[QualificationAnswerOutput] = Field(max_length=50)
    objection_phrase: str | None = Field(
        max_length=300,
        description=(
            "Set ONLY when the customer expresses a doubt, hesitation, or pushback about moving "
            "forward -- price pushback, 'let me think about it', 'not sure this is for me', 'does this "
            "actually work for my situation'. A short VERBATIM phrase copied from the customer's own "
            "words, never a paraphrase. Null whenever the message is a plain fact, a request for a "
            "service, an emergency, hostile, or an explicit advice/opinion request -- those are handled "
            "by confidence/requires_human above, not this field. An objection is a normal, low-risk part "
            "of a sales conversation and must NOT by itself raise requires_human or lower confidence."
        ),
    )
    customer_tone: CustomerTone = Field(
        description=(
            "The emotional register of THIS message only, classified from wording alone -- neutral "
            "(plain, matter-of-fact), irritated (curt, frustrated, complaining), anxious (worried, "
            "uncertain, seeking reassurance), urgent (pressed for time, wants speed, may overlap with "
            "urgency above but is about how they're writing, not how time-critical the service is), or "
            "playful (casual, joking, informal). Purely descriptive -- like objection_phrase, this must "
            "NEVER influence confidence, requires_human, service_id, or any other field above; a "
            "message can be irritated or anxious and still be a perfectly clear, low-risk request."
        ),
    )


class ClarificationOutput(StrictAIModel):
    addressed_items: list[str] = Field(max_length=50)
    message_text: str = Field(min_length=1, max_length=1_500)


class CustomerMessageOutput(StrictAIModel):
    response_type: Literal["not_qualified", "human_escalation"]
    message_text: str = Field(min_length=1, max_length=1_500)


class ReassuranceOutput(StrictAIModel):
    selected_trigger_description: str = Field(
        min_length=1,
        max_length=300,
        description=(
            "Copied EXACTLY (character for character) from one entry's trigger_description in "
            "APPROVED_OBJECTION_RESPONSES -- the entry whose approved_response actually answers the "
            "customer's objection. Never invented, never edited."
        ),
    )
    message_text: str = Field(
        min_length=1,
        max_length=800,
        description=(
            "A rephrasing of ONLY that entry's approved_response, adapted for tone -- must not add any "
            "fact, promise, price, or commitment that isn't already in the approved_response text."
        ),
    )


class UniversalReassuranceOutput(StrictAIModel):
    """Zero-config counterpart to ReassuranceOutput -- used when the business has not
    authored any objection_responses entries. No closed set to select from, so the
    model classifies the objection and writes a short acknowledgment grounded only in
    the facts given in context; SYSTEM_CONSTRAINTS and the caller's safety screen are
    what keep it from inventing a price, discount, guarantee, or promise."""

    objection_category: Literal[
        "price", "timing", "trust", "comparison", "fit", "consult_someone_else", "other"
    ]
    message_text: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "A brief, natural acknowledgment of the customer's specific concern, in your own words "
            "-- vary the phrasing rather than reusing a fixed template. Grounded only in facts present "
            "in BUSINESS_CONTEXT; must not state a price, discount, guarantee, or timeline that isn't "
            "there. Must not itself ask a question or try to close the conversation -- the calling "
            "code appends the next step separately."
        ),
    )


@dataclass(frozen=True, slots=True)
class AIInvocationMetadata:
    provider: str
    model: str
    prompt_id: str
    prompt_version: str
    decision_type: str
    latency_ms: int | None
    success: bool
    category: str
    attempts: int = 1
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("AI provider and model must not be empty")
        if self.attempts < 1:
            raise ValueError("AI attempts must be positive")
        for value in (self.latency_ms, self.input_tokens, self.output_tokens, self.total_tokens):
            if value is not None and value < 0:
                raise ValueError("AI latency and token counts cannot be negative")

    def with_attempts(self, attempts: int) -> "AIInvocationMetadata":
        return replace(self, attempts=attempts)

    def as_audit_dict(self, *, confidence: float | None = None) -> dict[str, object]:
        value: dict[str, object] = {
            "provider": self.provider,
            "model": self.model,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "decision_type": self.decision_type,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "category": self.category,
            "attempts": self.attempts,
        }
        if confidence is not None:
            value["confidence"] = confidence
        if self.input_tokens is not None:
            value["input_tokens"] = self.input_tokens
        if self.output_tokens is not None:
            value["output_tokens"] = self.output_tokens
        if self.total_tokens is not None:
            value["total_tokens"] = self.total_tokens
        return value


@dataclass(frozen=True, slots=True)
class AIRequest(Generic[StructuredOutput]):
    prompt_id: str
    prompt_version: str
    decision_type: str
    system_prompt: str
    user_prompt: str
    output_model: type[StructuredOutput]


@dataclass(frozen=True, slots=True)
class AIResult(Generic[StructuredOutput]):
    output: StructuredOutput
    metadata: AIInvocationMetadata
