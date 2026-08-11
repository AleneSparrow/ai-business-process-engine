"""Provider-neutral structured AI boundary."""

from .errors import (
    AIAuthenticationError,
    AIConfigurationError,
    AIInvalidOutputError,
    AIProviderError,
    AIProviderRequestError,
    AIRateLimitError,
    AITimeoutError,
    AITransportError,
)
from .models import AIInvocationMetadata, AIRequest, AIResult
from .provider import RetryingAIProvider, StructuredAIProvider

__all__ = [
    "AIAuthenticationError",
    "AIConfigurationError",
    "AIInvalidOutputError",
    "AIInvocationMetadata",
    "AIProviderError",
    "AIProviderRequestError",
    "AIRateLimitError",
    "AIRequest",
    "AIResult",
    "AITimeoutError",
    "AITransportError",
    "RetryingAIProvider",
    "StructuredAIProvider",
]
