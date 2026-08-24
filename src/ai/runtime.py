"""Runtime provider selection and engine-adapter assembly."""

from dataclasses import dataclass

from src.config import Settings
from src.engine.customer_response_generator import (
    CustomerResponseGenerator,
    DeterministicCustomerResponseGenerator,
)
from src.engine.intent_extractor import DeterministicIntentExtractor, IntentExtractor
from src.engine.question_generator import DeterministicQuestionGenerator, QuestionGenerator
from src.engine.reassurance_response_generator import (
    DeterministicReassuranceResponseGenerator,
    DeterministicUniversalReassuranceResponseGenerator,
    ReassuranceResponseGenerator,
    UniversalReassuranceResponseGenerator,
)

from .adapters import (
    AICustomerResponseGenerator,
    AIIntentExtractor,
    AIQuestionGenerator,
    AIReassuranceResponseGenerator,
    AIUniversalReassuranceResponseGenerator,
)
from .anthropic_provider import AnthropicProvider
from .fallback import (
    FallbackIntentExtractor,
    wrap_customer_response_generator,
    wrap_question_generator,
    wrap_reassurance_response_generator,
    wrap_universal_reassurance_response_generator,
)
from .openai_provider import OpenAIProvider
from .provider import RetryingAIProvider


@dataclass(frozen=True, slots=True)
class AIRuntimeComponents:
    intent_extractor: IntentExtractor
    question_generator: QuestionGenerator
    customer_response_generator: CustomerResponseGenerator
    reassurance_response_generator: ReassuranceResponseGenerator
    universal_reassurance_response_generator: UniversalReassuranceResponseGenerator
    provider_name: str
    model_name: str



def _with_deterministic_fallback(
    provider_name: str,
    model_name: str,
    intent_extractor: IntentExtractor,
    question_generator: QuestionGenerator,
    customer_response_generator: CustomerResponseGenerator,
    reassurance_response_generator: ReassuranceResponseGenerator,
    universal_reassurance_response_generator: UniversalReassuranceResponseGenerator,
) -> AIRuntimeComponents:
    """Wrap every AI component so a provider outage degrades instead of failing.

    Added 2026-08-23 after a live incident: the Anthropic credit balance ran
    out, intent extraction raised, and the public conversation endpoint
    returned 503 -- the widget then showed the raw error to a customer on the
    firm's own website. The deterministic implementations already exist and
    are what AI_PROVIDER=deterministic runs, so falling back to them keeps
    the sales cycle moving through an outage. See src/ai/fallback.py.
    """
    return AIRuntimeComponents(
        FallbackIntentExtractor(intent_extractor, DeterministicIntentExtractor()),
        wrap_question_generator(question_generator, DeterministicQuestionGenerator()),
        wrap_customer_response_generator(
            customer_response_generator, DeterministicCustomerResponseGenerator()
        ),
        wrap_reassurance_response_generator(
            reassurance_response_generator, DeterministicReassuranceResponseGenerator()
        ),
        wrap_universal_reassurance_response_generator(
            universal_reassurance_response_generator,
            DeterministicUniversalReassuranceResponseGenerator(),
        ),
        provider_name,
        model_name,
    )


def build_ai_runtime(settings: Settings) -> AIRuntimeComponents:
    if settings.ai_provider == "deterministic":
        return AIRuntimeComponents(
            DeterministicIntentExtractor(),
            DeterministicQuestionGenerator(),
            DeterministicCustomerResponseGenerator(),
            DeterministicReassuranceResponseGenerator(),
            DeterministicUniversalReassuranceResponseGenerator(),
            "deterministic",
            "deterministic-v1",
        )
    if settings.ai_provider == "anthropic":
        if settings.anthropic_api_key is None or settings.anthropic_model is None:
            raise RuntimeError("Anthropic runtime configuration is incomplete")
        provider = RetryingAIProvider(
            AnthropicProvider(
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model,
                timeout_seconds=settings.ai_timeout_seconds,
            ),
            max_retries=settings.ai_max_retries,
        )
        return _with_deterministic_fallback(
            "anthropic",
            settings.anthropic_model,
            AIIntentExtractor(provider),
            AIQuestionGenerator(provider),
            AICustomerResponseGenerator(provider),
            AIReassuranceResponseGenerator(provider),
            AIUniversalReassuranceResponseGenerator(provider),
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
    return _with_deterministic_fallback(
        "openai",
        settings.openai_model,
        AIIntentExtractor(provider),
        AIQuestionGenerator(provider),
        AICustomerResponseGenerator(provider),
        AIReassuranceResponseGenerator(provider),
        AIUniversalReassuranceResponseGenerator(provider),
    )
