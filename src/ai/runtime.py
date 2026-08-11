"""Runtime provider selection and engine-adapter assembly."""

from dataclasses import dataclass

from src.config import Settings
from src.engine.customer_response_generator import (
    CustomerResponseGenerator,
    DeterministicCustomerResponseGenerator,
)
from src.engine.intent_extractor import DeterministicIntentExtractor, IntentExtractor
from src.engine.question_generator import DeterministicQuestionGenerator, QuestionGenerator

from .adapters import AICustomerResponseGenerator, AIIntentExtractor, AIQuestionGenerator
from .openai_provider import OpenAIProvider
from .provider import RetryingAIProvider


@dataclass(frozen=True, slots=True)
class AIRuntimeComponents:
    intent_extractor: IntentExtractor
    question_generator: QuestionGenerator
    customer_response_generator: CustomerResponseGenerator
    provider_name: str
    model_name: str


def build_ai_runtime(settings: Settings) -> AIRuntimeComponents:
    if settings.ai_provider == "deterministic":
        return AIRuntimeComponents(
            DeterministicIntentExtractor(),
            DeterministicQuestionGenerator(),
            DeterministicCustomerResponseGenerator(),
            "deterministic",
            "deterministic-v1",
        )
    if settings.ai_provider != "openai":
        raise RuntimeError(f"unsupported AI_PROVIDER: {settings.ai_provider}")
    if settings.openai_api_key is None or settings.openai_model is None:
        raise RuntimeError("OpenAI runtime configuration is incomplete")
    provider = RetryingAIProvider(
        OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.ai_timeout_seconds,
        ),
        max_retries=settings.ai_max_retries,
    )
    return AIRuntimeComponents(
        AIIntentExtractor(provider),
        AIQuestionGenerator(provider),
        AICustomerResponseGenerator(provider),
        "openai",
        settings.openai_model,
    )
