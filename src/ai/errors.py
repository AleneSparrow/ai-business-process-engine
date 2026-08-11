"""Typed, safe AI failures that never include provider response bodies."""

from src.ai.models import AIInvocationMetadata


class AIProviderError(RuntimeError):
    category = "provider_error"
    transient = False

    def __init__(
        self,
        message: str,
        *,
        metadata: AIInvocationMetadata | None = None,
    ) -> None:
        super().__init__(message)
        self.metadata = metadata


class AIConfigurationError(AIProviderError):
    category = "configuration"


class AIAuthenticationError(AIProviderError):
    category = "authentication"


class AIInvalidOutputError(AIProviderError):
    category = "invalid_output"


class AIProviderRequestError(AIProviderError):
    category = "provider_request"


class AITimeoutError(AIProviderError):
    category = "timeout"
    transient = True


class AIRateLimitError(AIProviderError):
    category = "rate_limit"
    transient = True


class AITransportError(AIProviderError):
    category = "transport"
    transient = True


class AIInternalProviderError(AIProviderError):
    category = "provider_internal"
    transient = True
