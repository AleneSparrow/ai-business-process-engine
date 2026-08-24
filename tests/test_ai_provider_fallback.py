"""A provider outage must degrade the conversation, never break the widget.

Regression cover for the 2026-08-23 production incident: the Anthropic credit
balance ran out, intent extraction raised AIProviderRequestError, the public
conversation endpoint answered 503, and the chat widget rendered the raw
server message to a customer on a law firm's own website.

Runs without fastapi/sqlalchemy so it also executes in the cloud sandbox.
"""

from src.ai.errors import (
    AIAuthenticationError,
    AIInvalidOutputError,
    AIProviderRequestError,
    AIRateLimitError,
    AITimeoutError,
)
from src.ai.fallback import FallbackGenerator, FallbackIntentExtractor
from src.domain.qualification import IncomingMessage, IntentResult, Urgency
from src.domain.models import utc_now


CREDIT_EXHAUSTED = (
    "Claude rejected the structured request: Your credit balance is too low"
)


class _Exploding:
    """Stands in for an AI component whose provider is failing."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    def extract(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        raise self._error

    def generate(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        raise self._error


class _Deterministic:
    """Stands in for the deterministic implementation that must take over."""

    def __init__(self) -> None:
        self.calls = 0
        self.received: tuple[object, ...] = ()
        self.received_kwargs: dict[str, object] = {}

    def extract(self, message: object, business_dna: object) -> IntentResult:
        self.calls += 1
        self.received = (message, business_dna)
        return IntentResult(urgency=Urgency.NORMAL, confidence=0.5, requires_human=False)

    def generate(self, *args: object, **kwargs: object) -> str:
        self.calls += 1
        self.received = args
        self.received_kwargs = dict(kwargs)
        return "deterministic reply"


def _message() -> IncomingMessage:
    return IncomingMessage(
        "test-law-firm", "webchat", "m1", "I need help with a custody agreement", utc_now()
    )


def test_credit_exhaustion_falls_back_instead_of_raising():
    """The exact production failure: no credit left on the API account."""
    primary = _Exploding(AIProviderRequestError(CREDIT_EXHAUSTED))
    deterministic = _Deterministic()

    result = FallbackIntentExtractor(primary, deterministic).extract(_message(), {})

    assert primary.calls == 1
    assert deterministic.calls == 1
    assert isinstance(result, IntentResult)


def test_every_transient_provider_failure_falls_back():
    for error in (
        AITimeoutError("timed out"),
        AIRateLimitError("rate limited"),
        AIAuthenticationError("bad key"),
        AIProviderRequestError(CREDIT_EXHAUSTED),
    ):
        deterministic = _Deterministic()
        FallbackIntentExtractor(_Exploding(error), deterministic).extract(_message(), {})
        assert deterministic.calls == 1, f"no fallback for {type(error).__name__}"


def test_generator_falls_back_and_forwards_arguments_untouched():
    """Protocols differ per generator and gain keyword-only params over time."""
    deterministic = _Deterministic()
    wrapper = FallbackGenerator(
        _Exploding(AIProviderRequestError(CREDIT_EXHAUSTED)), deterministic, "question_generator"
    )

    assert wrapper.generate("a", "b", customer_tone="anxious") == "deterministic reply"
    assert deterministic.received == ("a", "b")
    assert deterministic.received_kwargs == {"customer_tone": "anxious"}


def test_healthy_provider_is_not_touched_by_the_wrapper():
    class _Working:
        def extract(self, message: object, business_dna: object) -> IntentResult:
            return IntentResult(urgency=Urgency.HIGH, confidence=0.95, requires_human=False)

    deterministic = _Deterministic()
    result = FallbackIntentExtractor(_Working(), deterministic).extract(_message(), {})

    assert deterministic.calls == 0
    assert result.confidence == 0.95


def test_our_own_bugs_are_not_masked():
    """Only provider failures degrade. A real defect must still surface.

    AIInvalidOutputError is handled inside the adapters themselves, and
    anything that is not an AIProviderError at all -- a TypeError from our
    own code -- must reach the caller instead of being hidden behind a
    plain-sounding reply.
    """
    deterministic = _Deterministic()
    wrapper = FallbackGenerator(_Exploding(TypeError("bug in our code")), deterministic, "x")
    try:
        wrapper.generate()
    except TypeError:
        pass
    else:
        raise AssertionError("a non-provider error must not be swallowed")
    assert deterministic.calls == 0

    extractor = FallbackIntentExtractor(_Exploding(AIInvalidOutputError("bad shape")), deterministic)
    try:
        extractor.extract(_message(), {})
    except AIInvalidOutputError:
        raise AssertionError("AIInvalidOutputError is an AIProviderError and should fall back")
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"unexpected error: {exc!r}") from exc
    assert deterministic.calls == 1
