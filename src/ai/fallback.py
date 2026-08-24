"""Last-resort degradation when the AI provider itself is unavailable.

Found in production on 2026-08-23: the Anthropic credit balance ran out, the
intent extraction call raised AIProviderRequestError, and the public
conversation endpoint answered 503. The chat widget rendered the raw server
message -- a customer on a law firm's website was shown "The configured AI
provider is unavailable" in red. That is a lost lead and a site that looks
broken, over an infrastructure problem the customer has nothing to do with.

The engine already has a complete deterministic implementation of every
generator (it is what AI_PROVIDER=deterministic runs, and it is exercised by
the whole test suite). These wrappers make it the automatic fallback: if the
provider fails for any reason -- no credit, rate limit, timeout, transport,
bad key, or a business whose ai_permissions forbid the capability -- the
conversation continues deterministically instead of erroring out. The
customer notices a plainer wording, never a failure.

Every fallback is logged as a distinct event so a degraded deployment is
visible in operations rather than silent: an AI outage must not look like
business as usual on the dashboards.

Deliberately NOT caught here: anything that is not an AIProviderError.
AIInvalidOutputError is already handled inside the adapters themselves (they
degrade a single field or fall back per generator); a genuine bug in our own
code must still surface as a 500 rather than be masked as a plain reply.
"""

import json
import logging
from typing import Any

from src.domain.qualification import IncomingMessage, IntentResult
from src.engine.customer_response_generator import CustomerResponseGenerator
from src.engine.intent_extractor import IntentExtractor
from src.engine.question_generator import QuestionGenerator
from src.engine.reassurance_response_generator import (
    ReassuranceResponseGenerator,
    UniversalReassuranceResponseGenerator,
)

from .errors import AIProviderError

from collections.abc import Mapping

_LOGGER = logging.getLogger("uvicorn.error")


def _log_fallback(component: str, exc: AIProviderError) -> None:
    """Record the degradation. Never includes provider response bodies.

    `category` comes from the typed error class (src/ai/errors.py), so it
    says which failure this was -- rate_limit, timeout, provider_request,
    authentication -- without logging customer content or credentials.
    """
    _LOGGER.log(
        logging.WARNING,
        json.dumps(
            {
                "event": "ai_provider_unavailable_fallback_to_deterministic",
                "component": component,
                "category": getattr(exc, "category", "provider_error"),
                "transient": getattr(exc, "transient", False),
            },
            separators=(",", ":"),
            default=str,
        ),
    )


class FallbackIntentExtractor:
    """AI intent extraction, degrading to the deterministic extractor."""

    def __init__(self, primary: IntentExtractor, deterministic: IntentExtractor) -> None:
        self._primary = primary
        self._deterministic = deterministic

    def extract(
        self, message: IncomingMessage, business_dna: Mapping[str, object]
    ) -> IntentResult:
        try:
            return self._primary.extract(message, business_dna)
        except AIProviderError as exc:
            _log_fallback("intent_extractor", exc)
            return self._deterministic.extract(message, business_dna)


class FallbackGenerator:
    """Any AI generator, degrading to its deterministic counterpart.

    Arguments are forwarded untouched, so this stays correct as the
    generator protocols evolve (they differ from each other and gain
    keyword-only parameters like customer_tone over time).
    """

    def __init__(self, primary: Any, deterministic: Any, component: str) -> None:
        self._primary = primary
        self._deterministic = deterministic
        self._component = component

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._primary.generate(*args, **kwargs)
        except AIProviderError as exc:
            _log_fallback(self._component, exc)
            return self._deterministic.generate(*args, **kwargs)


def wrap_question_generator(
    primary: QuestionGenerator, deterministic: QuestionGenerator
) -> QuestionGenerator:
    return FallbackGenerator(primary, deterministic, "question_generator")


def wrap_customer_response_generator(
    primary: CustomerResponseGenerator, deterministic: CustomerResponseGenerator
) -> CustomerResponseGenerator:
    return FallbackGenerator(primary, deterministic, "customer_response_generator")


def wrap_reassurance_response_generator(
    primary: ReassuranceResponseGenerator, deterministic: ReassuranceResponseGenerator
) -> ReassuranceResponseGenerator:
    return FallbackGenerator(primary, deterministic, "reassurance_response_generator")


def wrap_universal_reassurance_response_generator(
    primary: UniversalReassuranceResponseGenerator,
    deterministic: UniversalReassuranceResponseGenerator,
) -> UniversalReassuranceResponseGenerator:
    return FallbackGenerator(
        primary, deterministic, "universal_reassurance_response_generator"
    )
