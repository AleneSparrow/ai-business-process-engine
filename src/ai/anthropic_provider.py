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
        system_blocks = self._system_blocks(request.system_prompt)
        user_content = self._user_content(request.user_prompt, request.user_prompt_cache_prefix)
        try:
            output = None
            usage = None
            last_shape_error: str | None = None
            for _ in range(_MAX_STRUCTURED_OUTPUT_ATTEMPTS):
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=_MAX_OUTPUT_TOKENS,
                    # NOTE: deliberately no `temperature` param. A prior
                    # version of this file set temperature=0 to narrow
                    # decision-boundary sampling variance (the same test
                    # message flipping between QUALIFYING and NEEDS_HUMAN
                    # across identical requests) -- but claude-sonnet-5
                    # rejects it outright with a 400 ("`temperature` is
                    # deprecated for this model"), which took the whole
                    # provider down, not just the variance it was meant to
                    # fix. Confirmed live via Railway logs before reverting.
                    # If reducing sampling variance is worth revisiting,
                    # check the current model's docs for its replacement
                    # (if any) before reintroducing a sampling parameter.
                    system=system_blocks,
                    messages=[{"role": "user", "content": user_content}],
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
            # Anthropic reports these as two separate counters alongside
            # input_tokens (which itself excludes both) -- present only when
            # caching was actually attempted for this request, never 0 as a
            # stand-in for "cache not used". See task-cost-reduction.md: this
            # is what makes measuring the real hit rate possible instead of
            # assuming it.
            cache_read_tokens = getattr(usage, "cache_read_input_tokens", None)
            cache_write_tokens = getattr(usage, "cache_creation_input_tokens", None)
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
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
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
                f"Claude authentication or permission failed: {exc}",
                metadata=self._metadata(request, started, success=False, category="authentication"),
            ) from exc
        except APIConnectionError as exc:
            raise AITransportError(
                "Claude network request failed",
                metadata=self._metadata(request, started, success=False, category="transport"),
            ) from exc
        except APIStatusError as exc:
            # exc's own message is Anthropic's own account/request-status text
            # (e.g. a workspace spend limit or invalid-request reason) --
            # never customer-submitted content -- safe to log as-is.
            error_type = AIInternalProviderError if exc.status_code >= 500 else AIProviderRequestError
            category = "provider_internal" if exc.status_code >= 500 else "provider_request"
            raise error_type(
                f"Claude rejected the structured request: {exc}",
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
        cache_read_tokens: int | None = None,
        cache_write_tokens: int | None = None,
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
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )

    @staticmethod
    def _system_blocks(system_prompt: str) -> list[dict[str, Any]]:
        """The system prompt is fully static per prompt_id (see prompts.py --
        it never includes Business DNA or conversation content), so it is
        always cache-eligible, unconditionally, for every request. See
        task-cost-reduction.md lever 1."""
        return [{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }]

    @staticmethod
    def _user_content(user_prompt: str, cache_prefix: str) -> list[dict[str, Any]]:
        """Second, optional cache_control breakpoint after the Business-DNA
        prefix of the user message (see Prompt.user_cache_prefix) -- stable
        across many messages for the same business, unlike the conversation/
        customer-message tail that follows it. Falls back to a single
        uncached block whenever the caller didn't supply a genuine prefix
        (empty, or -- defensively -- not actually a prefix of user_prompt),
        which is always correct, just not cached."""
        if cache_prefix and user_prompt.startswith(cache_prefix):
            return [
                {
                    "type": "text",
                    "text": cache_prefix,
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": user_prompt[len(cache_prefix):]},
            ]
        return [{"type": "text", "text": user_prompt}]
