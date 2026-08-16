"""Official Anthropic SDK adapter using forced tool-use for structured output.

Claude has no direct equivalent to OpenAI Responses API's `text_format`
Pydantic parsing. Structured output is obtained instead by declaring a
single tool whose `input_schema` is the request's Pydantic model's JSON
schema, forcing Claude to call it (`tool_choice={"type": "tool", ...}`), and
validating the tool call's `input` against that same model. This keeps the
exact `AIRequest` in / `AIResult` out contract `OpenAIProvider` uses, so
nothing above this file -- `adapters.py`'s post-hoc safety filtering,
`prompts.py`'s rewrite-only / no-improvisation system prompt, or
`runtime.py`'s provider selection -- has to know which vendor is behind
AI_PROVIDER. Swapping providers changes only which model executes an
already-constrained prompt against an already-constrained schema; it does
not touch either guardrail layer.
"""

from time import perf_counter
from typing import Any, TypeVar

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
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

# Fixed name for the single forced tool call -- never seen by the model as a
# real "choice" among tools, just the schema-shaped output channel.
_TOOL_NAME = "emit_structured_output"

# Structured outputs here are small (short message text, a handful of typed
# fields) -- this is headroom, not a real generation budget.
_MAX_OUTPUT_TOKENS = 4096

# Unlike OpenAI's Responses API `.parse()`, which constrains decoding so the
# output is schema-valid by construction, Claude's forced tool-use is not a
# hard guarantee -- on rare, usually unusual/edge-case inputs it can omit a
# required field or skip the tool call. A fresh sample of the *same* request
# fixes this in practice, so a shape-invalid attempt is resampled this many
# times (1 = no resample) before it becomes a permanent AIInvalidOutputError.
# This is deliberately internal to this provider and separate from
# `AIInvalidOutputError.transient` (False for every provider, at the
# RetryingAIProvider layer) -- that flag governs retrying a request that
# already failed cleanly; this loop exists because Claude's failure mode
# here is "asked again, got it right," not "failed for a durable reason."
_MAX_STRUCTURED_OUTPUT_ATTEMPTS = 3


class AnthropicProvider:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        if not api_key.strip():
            raise ValueError("Anthropic API key must not be empty")
        if not model.strip():
            raise ValueError("Anthropic model must not be empty")
        if not 0 < timeout_seconds <= 120:
            raise ValueError("AI timeout must be greater than 0 and at most 120 seconds")
        self.model = model
        self._client = Anthropic(api_key=api_key, timeout=timeout_seconds, max_retries=0)

    def generate(self, request: AIRequest[OutputT]) -> AIResult[OutputT]:
        started = perf_counter()
        schema = request.output_model.model_json_schema()
        try:
            output = None
            usage = None
            last_shape_error: str | None = None
            for _ in range(_MAX_STRUCTURED_OUTPUT_ATTEMPTS):
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=_MAX_OUTPUT_TOKENS,
                    # Every request through this provider is a structured
                    # extraction/classification/rewrite task, not open-ended
                    # generation -- the same customer message should reach
                    # the same qualification decision every time it
                    # reasonably can. Low temperature doesn't make this
                    # provider fully deterministic (no LLM API guarantees
                    # that even at temperature=0), but it substantially
                    # narrows the sampling variance observed live: the exact
                    # same test message flipped between QUALIFYING and
                    # NEEDS_HUMAN across otherwise-identical requests.
                    temperature=0,
                    system=request.system_prompt,
                    messages=[{"role": "user", "content": request.user_prompt}],
                    tools=[
                        {
                            "name": _TOOL_NAME,
                            "description": (
                                "Return the requested structured output. This is the only "
                                "allowed response -- do not reply with free-form text. You "
                                "MUST include every property defined in the schema, with no "
                                "exceptions: use null for any nullable property that doesn't "
                                "apply, and an empty array for a list property with nothing "
                                "to report. Never omit a property because it seems "
                                "irrelevant -- an omitted property is treated as an error, "
                                "not a smaller/leaner response."
                            ),
                            "input_schema": schema,
                        }
                    ],
                    tool_choice={"type": "tool", "name": _TOOL_NAME},
                )
                tool_use = next(
                    (block for block in response.content if block.type == "tool_use"), None
                )
                if tool_use is None:
                    last_shape_error = "Claude returned no tool call"
                    continue
                try:
                    output = request.output_model.model_validate(tool_use.input)
                except ValidationError as exc:
                    # Field path + pydantic error type only -- never the
                    # offending value, which may be customer-submitted text
                    # (name, phone, notes...). Safe to log as-is.
                    safe_detail = "; ".join(
                        f"{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                        for error in exc.errors()
                    )
                    last_shape_error = f"Claude returned invalid structured output ({safe_detail})"
                    continue
                usage = getattr(response, "usage", None)
                break

            if output is None:
                raise AIInvalidOutputError(
                    last_shape_error or "Claude returned invalid structured output",
                    metadata=self._metadata(request, started, success=False, category="invalid_output"),
                )
            input_tokens = getattr(usage, "input_tokens", None)
            output_tokens = getattr(usage, "output_tokens", None)
            metadata = self._metadata(
                request,
                started,
                success=True,
                category="success",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=(
                    input_tokens + output_tokens
                    if input_tokens is not None and output_tokens is not None
                    else None
                ),
            )
            return AIResult(output, metadata)
        except AIInvalidOutputError:
            raise
        except APITimeoutError as exc:
            raise AITimeoutError(
                "Claude request timed out",
                metadata=self._metadata(request, started, success=False, category="timeout"),
            ) from exc
        except RateLimitError as exc:
            raise AIRateLimitError(
                "Claude rate limit reached",
                metadata=self._metadata(request, started, success=False, category="rate_limit"),
            ) from exc
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise AIAuthenticationError(
                "Claude authentication or permission failed",
                metadata=self._metadata(request, started, success=False, category="authentication"),
            ) from exc
        except APIConnectionError as exc:
            raise AITransportError(
                "Claude network request failed",
                metadata=self._metadata(request, started, success=False, category="transport"),
            ) from exc
        except APIStatusError as exc:
            error_type = AIInternalProviderError if exc.status_code >= 500 else AIProviderRequestError
            category = "provider_internal" if exc.status_code >= 500 else "provider_request"
            raise error_type(
                "Claude rejected the structured request",
                metadata=self._metadata(request, started, success=False, category=category),
            ) from exc
        except Exception as exc:
            raise AIInternalProviderError(
                "Claude provider failed unexpectedly",
                metadata=self._metadata(request, started, success=False, category="provider_internal"),
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
            provider="anthropic",
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
