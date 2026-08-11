"""Typed requests, outputs, and safe audit metadata for AI providers."""

from dataclasses import dataclass, replace
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from src.domain.qualification import Urgency


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class StrictAIModel(BaseModel):
    """Base for provider responses; unknown fields are always rejected."""

    model_config = ConfigDict(extra="forbid")


class QualificationAnswerOutput(StrictAIModel):
    question_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(min_length=1, max_length=500)


class IntentOutput(StrictAIModel):
    service_id: str | None = Field(max_length=128)
    unsupported_service: bool
    unsupported_service_name: str | None = Field(max_length=200)
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


class ClarificationOutput(StrictAIModel):
    addressed_items: list[str] = Field(max_length=50)
    message_text: str = Field(min_length=1, max_length=1_500)


class CustomerMessageOutput(StrictAIModel):
    response_type: Literal["not_qualified", "human_escalation"]
    message_text: str = Field(min_length=1, max_length=1_500)


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
