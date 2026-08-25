"""Zero-config service matching: semantic mapping with an evidence guarantee.

Covers AIIntentExtractor._resolve_service after the 2026-08-22 change that
replaced literal catalog-term matching (plus the single-service bypass added
2026-08-17) with a customer-quote evidence check. The point of the change is
that intake must work with NO owner configuration in ANY vertical -- a
customer writes their own words, never the service label -- while keeping the
guarantee that the model can invent neither the service nor its justification.

Deliberately imports only src.ai + src.domain so it runs in the sandbox, where
fastapi/sqlalchemy/pytest are unavailable (see tests/test_ai.py, which cannot).
"""

from src.ai.adapters import AIIntentExtractor
from src.ai.errors import AIInvalidOutputError
from src.ai.models import IntentOutput


def _output(**changes: object) -> IntentOutput:
    value: dict[str, object] = {
        "service_id": None,
        "unsupported_service": False,
        "unsupported_service_name": None,
        "service_evidence": None,
        "urgency": "normal",
        "customer_location": None,
        "preferred_time": None,
        "notes": None,
        "customer_name": None,
        "phone": None,
        "email": None,
        "confidence": 0.95,
        "requires_human": False,
        "unintelligible": False,
        "qualification_answers": [],
        "objection_phrase": None,
        "customer_tone": "neutral",
    }
    value.update(changes)
    return IntentOutput.model_validate(value)


# A solo legal practice as onboarding actually builds it: one generic service,
# aliases defaulting to just the service's own name.
SOLO_LEGAL = [
    {
        "id": "consultation",
        "name": "Consultation",
        "description": "Family law matters: divorce, custody, child support",
        "aliases": ["consultation"],
        "qualification_questions": [],
    }
]

# A multi-service business outside the legal vertical -- the case the previous
# single-service bypass never covered.
HOME_REPAIRS = [
    {
        "id": "roof-repair",
        "name": "Roof Repair",
        "description": "Fixing leaks, storm damage, and missing shingles",
        "aliases": ["roof repair"],
        "qualification_questions": [],
    },
    {
        "id": "drain-cleaning",
        "name": "Drain Cleaning",
        "description": "Clearing blocked or slow drains and sewer lines",
        "aliases": ["drain cleaning"],
        "qualification_questions": [],
    },
]


def test_customer_words_resolve_service_without_configured_keywords():
    """The whole point: 'my divorce' must reach a service named 'Consultation'."""
    message = "I need help with my divorce and I don't know where to start."
    resolved, unsupported = AIIntentExtractor._resolve_service(
        _output(service_id="consultation", service_evidence="help with my divorce"),
        SOLO_LEGAL,
        message,
    )
    assert resolved == "consultation"
    assert unsupported is None


def test_multi_service_business_resolves_by_meaning_not_label():
    """Multi-service, non-legal: previously impossible without manual synonyms."""
    message = "My roof has been leaking ever since the storm on Tuesday."
    resolved, unsupported = AIIntentExtractor._resolve_service(
        _output(service_id="roof-repair", service_evidence="roof has been leaking"),
        HOME_REPAIRS,
        message,
    )
    assert resolved == "roof-repair"
    assert unsupported is None


def test_multi_service_business_picks_the_other_service_by_meaning():
    message = "the kitchen sink is backing up again, water won't go down"
    resolved, unsupported = AIIntentExtractor._resolve_service(
        _output(service_id="drain-cleaning", service_evidence="water won't go down"),
        HOME_REPAIRS,
        message,
    )
    assert resolved == "drain-cleaning"
    assert unsupported is None


def test_invented_evidence_is_rejected():
    """The anti-hallucination guarantee: the quote must be the customer's words."""
    message = "I need help with my divorce."
    try:
        AIIntentExtractor._resolve_service(
            _output(
                service_id="consultation",
                service_evidence="my roof is leaking",
            ),
            SOLO_LEGAL,
            message,
        )
    except AIInvalidOutputError as exc:
        assert "without customer evidence" in str(exc)
    else:
        raise AssertionError("invented evidence must be rejected")


def test_missing_evidence_is_rejected_even_for_single_service_business():
    """Regression: the 2026-08-17 single-service bypass removed this check entirely."""
    message = "Hello?"
    try:
        AIIntentExtractor._resolve_service(
            _output(service_id="consultation", service_evidence=None),
            SOLO_LEGAL,
            message,
        )
    except AIInvalidOutputError as exc:
        assert "without customer evidence" in str(exc)
    else:
        raise AssertionError("a single-service catalog must still require evidence")


def test_service_outside_catalog_is_rejected():
    message = "I need a tax audit."
    try:
        AIIntentExtractor._resolve_service(
            _output(service_id="tax-audit", service_evidence="a tax audit"),
            SOLO_LEGAL,
            message,
        )
    except AIInvalidOutputError as exc:
        assert "outside the supplied catalog" in str(exc)
    else:
        raise AssertionError("a service not in the catalog must be rejected")


def test_known_service_needs_no_fresh_evidence():
    """A bare answer to a question we asked must not re-escalate."""
    resolved, unsupported = AIIntentExtractor._resolve_service(
        _output(service_id="consultation", service_evidence=None),
        SOLO_LEGAL,
        "555-201-3344",
        known_service="consultation",
    )
    assert resolved == "consultation"
    assert unsupported is None


def test_evidence_match_is_case_insensitive():
    message = "MY ROOF IS LEAKING, please help"
    resolved, unsupported = AIIntentExtractor._resolve_service(
        _output(service_id="roof-repair", service_evidence="my roof is leaking"),
        HOME_REPAIRS,
        message,
    )
    assert resolved == "roof-repair"
    assert unsupported is None


def test_unsupported_service_path_still_requires_verbatim_evidence():
    """Unchanged by this work, asserted here so the two paths stay distinct.

    The unsupported branch returns the customer's own phrase (not a catalog
    id); an invented phrase is still rejected.
    """
    message = "Do you do wedding photography?"
    resolved, unsupported = AIIntentExtractor._resolve_service(
        _output(
            service_id=None,
            unsupported_service=True,
            unsupported_service_name="wedding photography",
        ),
        HOME_REPAIRS,
        message,
    )
    # After 2026-08-25 the two are separate return slots: a service the
    # catalog does not have never masquerades as a resolved service id.
    assert resolved is None
    assert unsupported == "wedding photography"

    try:
        AIIntentExtractor._resolve_service(
            _output(
                service_id=None,
                unsupported_service=True,
                unsupported_service_name="pet grooming",
            ),
            HOME_REPAIRS,
            message,
        )
    except AIInvalidOutputError as exc:
        assert "invalid unsupported service" in str(exc)
    else:
        raise AssertionError("an invented unsupported-service name must be rejected")


def test_business_context_exposes_industry_and_description():
    context = AIIntentExtractor._business_context(
        {"business": {"industry": "Family law", "description": "Solo practice in California"}}
    )
    assert context == {"industry": "Family law", "description": "Solo practice in California"}


def test_business_context_tolerates_missing_fields():
    assert AIIntentExtractor._business_context({}) == {}
    assert AIIntentExtractor._business_context({"business": {}}) == {
        "industry": "",
        "description": "",
    }
