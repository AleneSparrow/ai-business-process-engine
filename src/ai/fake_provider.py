"""Controllable structured provider for tests; never performs network I/O."""

from collections import deque
from collections.abc import Iterable
from threading import Lock
from time import perf_counter
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import AIInvalidOutputError, AIProviderError
from .models import AIInvocationMetadata, AIRequest, AIResult


OutputT = TypeVar("OutputT", bound=BaseModel)


class FakeAIProvider:
    def __init__(
        self,
        outcomes: Iterable[BaseModel | dict[str, Any] | AIProviderError],
        *,
        model: str = "fake-structured-model",
    ) -> None:
        self._outcomes = deque(outcomes)
        self._lock = Lock()
        self.model = model
        self.call_count = 0
        self.requests: list[AIRequest[Any]] = []

    def generate(self, request: AIRequest[OutputT]) -> AIResult[OutputT]:
        started = perf_counter()
        with self._lock:
            self.call_count += 1
            self.requests.append(request)
            if not self._outcomes:
                raise AssertionError("fake AI provider has no configured outcome")
            outcome = self._outcomes.popleft()
        metadata = AIInvocationMetadata(
            provider="fake",
            model=self.model,
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            decision_type=request.decision_type,
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
            success=not isinstance(outcome, AIProviderError),
            category="success" if not isinstance(outcome, AIProviderError) else outcome.category,
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
        )
        if isinstance(outcome, AIProviderError):
            if outcome.metadata is None:
                outcome.metadata = metadata
            raise outcome
        try:
            output = request.output_model.model_validate(outcome)
        except ValidationError as exc:
            raise AIInvalidOutputError(
                "AI provider returned invalid structured output",
                metadata=AIInvocationMetadata(
                    provider="fake",
                    model=self.model,
                    prompt_id=request.prompt_id,
                    prompt_version=request.prompt_version,
                    decision_type=request.decision_type,
                    latency_ms=metadata.latency_ms,
                    success=False,
                    category="invalid_output",
                ),
            ) from exc
        return AIResult(output, metadata)
