"""Provider-backed language analysis for the asynchronous sales shadow worker."""

from dataclasses import dataclass
from typing import Any, Mapping

from src.domain.sales import SalesTurnAnalysis
from .models import AIInvocationMetadata, AIRequest
from .provider import StructuredAIProvider
from .sales_adapter import build_sales_turn_analysis
from .sales_models import SALES_PROMPT_VERSION, SalesTurnAnalysisOutput
from .sales_prompts import sales_turn_analysis_prompt


@dataclass(frozen=True, slots=True)
class AnalyzedSalesTurn:
    analysis: SalesTurnAnalysis
    metadata: AIInvocationMetadata


class AISalesTurnAnalyzer:
    def __init__(self, provider: StructuredAIProvider) -> None:
        self._provider = provider

    def analyze(self, *, source_message_id: str, customer_message: str,
                profile_context: Mapping[str, Any],
                conversation_context: Mapping[str, Any]) -> AnalyzedSalesTurn:
        prompt = sales_turn_analysis_prompt(
            profile_context=profile_context, conversation_context=conversation_context,
            customer_message=customer_message,
        )
        result = self._provider.generate(AIRequest(
            prompt.identifier, prompt.version, "sales_turn_analysis", prompt.system,
            prompt.user, SalesTurnAnalysisOutput,
            user_prompt_cache_prefix=prompt.user_cache_prefix,
        ))
        analysis = build_sales_turn_analysis(
            result.output, source_message_id=source_message_id,
            customer_message=customer_message,
            metadata={"prompt_version": SALES_PROMPT_VERSION, "model": result.metadata.model},
        )
        return AnalyzedSalesTurn(analysis, result.metadata)
