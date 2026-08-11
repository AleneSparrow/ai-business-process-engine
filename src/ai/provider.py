"""Provider protocol and bounded transient retry wrapper."""

import time
from random import uniform
from collections.abc import Callable
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .errors import AIProviderError
from .models import AIRequest, AIResult


OutputT = TypeVar("OutputT", bound=BaseModel)


class StructuredAIProvider(Protocol):
    def generate(self, request: AIRequest[OutputT]) -> AIResult[OutputT]: ...


class RetryingAIProvider:
    """Retries only errors explicitly classified as transient."""

    def __init__(
        self,
        provider: StructuredAIProvider,
        *,
        max_retries: int,
        initial_backoff_seconds: float = 0.1,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] | None = None,
    ) -> None:
        if not 0 <= max_retries <= 3:
            raise ValueError("AI max_retries must be between 0 and 3")
        if initial_backoff_seconds < 0:
            raise ValueError("AI retry backoff cannot be negative")
        self.provider = provider
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds
        self.sleep = sleep
        self.jitter = jitter or (lambda delay: uniform(delay * 0.8, delay * 1.2))

    def generate(self, request: AIRequest[OutputT]) -> AIResult[OutputT]:
        attempts = 0
        while True:
            attempts += 1
            try:
                result = self.provider.generate(request)
                return AIResult(result.output, result.metadata.with_attempts(attempts))
            except AIProviderError as exc:
                if not exc.transient or attempts > self.max_retries:
                    if exc.metadata is not None:
                        exc.metadata = exc.metadata.with_attempts(attempts)
                    raise
                delay = self.initial_backoff_seconds * (2 ** (attempts - 1))
                self.sleep(self.jitter(delay))
