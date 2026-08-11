"""Official OpenAI SDK adapter using typed Responses API parsing."""

from time import perf_counter
from typing import Any, TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from .errors import (
    AIAuthenticationError,
    AIInternalProviderError,
    AIInvalidOutputError,
    AIProviderRequestError,
    AIRateLimitError,
    AITimeoutError,
    AITransportError,
)
from .models import AIInvocationMetadata, AIRequest, AIResult


OutputT = TypeVar("OutputT", bound=BaseModel)


class OpenAIProvider:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        if not model.strip():
            raise ValueError("OpenAI model must not be empty")
        if not 0 < timeout_seconds <= 120:
            raise ValueError("AI timeout must be greater than 0 and at most 120 seconds")
        self.model = model
        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)

    def generate(self, request: AIRequest[OutputT]) -> AIResult[OutputT]:
        started = perf_counter()
        try:
            response = self._client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                text_format=request.output_model,
            )
            output = response.output_parsed
            if output is None:
                raise AIInvalidOutputError("OpenAI returned no usable structured output")
            if not isinstance(output, request.output_model):
                output = request.output_model.model_validate(output)
            usage = getattr(response, "usage", None)
            metadata = self._metadata(
                request,
                started,
                success=True,
                category="success",
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )
            return AIResult(output, metadata)
        except AIInvalidOutputError as exc:
            if exc.metadata is None:
                exc.metadata = self._metadata(request, started, success=False, category=exc.category)
            raise
        except ValidationError as exc:
            raise AIInvalidOutputError(
                "OpenAI returned invalid structured output",
                metadata=self._metadata(request, started, success=False, category="invalid_output"),
            ) from exc
        except APITimeoutError as exc:
            raise AITimeoutError(
                "OpenAI request timed out",
                metadata=self._metadata(request, started, success=False, category="timeout"),
            ) from exc
        except RateLimitError as exc:
            raise AIRateLimitError(
                "OpenAI rate limit reached",
                metadata=self._metadata(request, started, success=False, category="rate_limit"),
            ) from exc
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise AIAuthenticationError(
                "OpenAI authentication or permission failed",
                metadata=self._metadata(request, started, success=False, category="authentication"),
            ) from exc
        except APIConnectionError as exc:
            raise AITransportError(
                "OpenAI network request failed",
                metadata=self._metadata(request, started, success=False, category="transport"),
            ) from exc
        except APIStatusError as exc:
            error_type = AIInternalProviderError if exc.status_code >= 500 else AIProviderRequestError
            category = "provider_internal" if exc.status_code >= 500 else "provider_request"
            raise error_type(
                "OpenAI rejected the structured request",
                metadata=self._metadata(request, started, success=False, category=category),
            ) from exc
        except Exception as exc:
            raise AIInternalProviderError(
                "OpenAI provider failed unexpectedly",
                metadata=self._metadata(
                    request,
                    started,
                    success=False,
                    category="provider_internal",
                ),
            ) from exc

    def _metadata(
        self,
        request: AIRequest[Any],
        started: float,
        *,
        success: bool,
        category: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> AIInvocationMetadata:
        return AIInvocationMetadata(
            provider="openai",
            model=self.model,
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            decision_type=request.decision_type,
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
            success=success,
            category=category,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
