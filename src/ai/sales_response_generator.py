"""Provider-backed wording component for staff-only sales shadow evaluation."""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.domain.sales import SalesMove, SalesStage

from .models import AIInvocationMetadata, AIRequest
from .provider import StructuredAIProvider
from .sales_response_models import SalesResponseOutput
from .sales_response_prompts import sales_response_prompt


@dataclass(frozen=True, slots=True)
class SalesResponseGenerationInput:
    approved_move: SalesMove
    sales_stage: SalesStage
    channel: str
    customer_tone: str
    knowledge_cards: Sequence[Mapping[str, Any]]
    business_facts: Sequence[Mapping[str, Any]]
    customer_evidence: Sequence[Mapping[str, Any]]
    handoff_template: str | None
    safe_fallback_text: str | None
    conversation_context: Mapping[str, Any]
    customer_message: str


@dataclass(frozen=True, slots=True)
class GeneratedSalesResponse:
    output: SalesResponseOutput
    metadata: AIInvocationMetadata


class AISalesResponseGenerator:
    """Calls the provider but cannot persist or deliver the returned wording."""

    def __init__(self, provider: StructuredAIProvider) -> None:
        self._provider = provider

    def generate(self, value: SalesResponseGenerationInput) -> GeneratedSalesResponse:
        prompt = sales_response_prompt(
            approved_move=value.approved_move,
            sales_stage=value.sales_stage,
            channel=value.channel,
            customer_tone=value.customer_tone,
            knowledge_cards=value.knowledge_cards,
            business_facts=value.business_facts,
            customer_evidence=value.customer_evidence,
            handoff_template=value.handoff_template,
            safe_fallback_text=value.safe_fallback_text,
            conversation_context=value.conversation_context,
            customer_message=value.customer_message,
        )
        result = self._provider.generate(AIRequest(
            prompt.identifier,
            prompt.version,
            "sales_response_generation",
            prompt.system,
            prompt.user,
            SalesResponseOutput,
            user_prompt_cache_prefix=prompt.user_cache_prefix,
        ))
        return GeneratedSalesResponse(result.output, result.metadata)
