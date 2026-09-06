from datetime import datetime, timezone

import pytest

from src.domain.sales import SalesMove
from src.engine.sales_response_validator import (
    SalesPolicyValidator,
    SalesResponseCandidate,
    SalesResponseValidationContext,
)


def context(**overrides):
    values = {
        "approved_move": SalesMove.PRESENT_RELEVANT_VALUE,
        "approved_knowledge": frozenset({"knowledge-1"}),
        "approved_business_facts": {"price-1": "The plan costs $199 per month."},
        "customer_evidence": {"evidence-1": "I need faster follow-up"},
        "safe_fallback": "I’ll have someone follow up with you.",
    }
    values.update(overrides)
    return SalesResponseValidationContext(**values)


def candidate(**overrides):
    values = {
        "message_text": "This approach helps address the follow-up problem you described.",
        "move": SalesMove.PRESENT_RELEVANT_VALUE,
        "knowledge_ids": ("knowledge-1",),
        "business_fact_ids": (),
        "customer_evidence_ids": ("evidence-1",),
    }
    values.update(overrides)
    return SalesResponseCandidate(**values)


def test_valid_grounded_candidate_passes_without_fallback() -> None:
    result = SalesPolicyValidator().validate(candidate(), context(knowledge_required=True))
    assert result.valid is True
    assert result.used_fallback is False


@pytest.mark.parametrize(
    ("changed", "violation"),
    (
        ({"move": SalesMove.ASK_FOR_COMMITMENT}, "move_mismatch"),
        ({"knowledge_ids": ("invented",)}, "unapproved_knowledge_id"),
        ({"business_fact_ids": ("invented",)}, "unknown_business_fact_id"),
        ({"customer_evidence_ids": ("invented",)}, "unknown_customer_evidence_id"),
        ({"knowledge_ids": ("knowledge-1", "knowledge-1")}, "duplicate_knowledge_id"),
        ({"message_text": "  "}, "empty_message"),
    ),
)
def test_invalid_candidate_uses_deterministic_fallback(changed, violation) -> None:
    result = SalesPolicyValidator().validate(candidate(**changed), context())
    assert result.valid is False
    assert violation in result.violations
    assert result.message_text == context().safe_fallback
    assert result.used_fallback is True


def test_knowledge_required_move_cannot_improvise_without_card() -> None:
    result = SalesPolicyValidator().validate(
        candidate(knowledge_ids=()), context(knowledge_required=True)
    )
    assert "required_knowledge_missing" in result.violations


def test_knowledge_required_move_can_use_only_exact_server_fallback() -> None:
    safe = "I don’t have an approved answer for that, so I’ll ask a person to follow up."
    accepted = SalesPolicyValidator().validate(
        candidate(message_text=safe, knowledge_ids=(), used_safe_fallback=True),
        context(knowledge_required=True, safe_fallback=safe),
    )
    paraphrased = SalesPolicyValidator().validate(
        candidate(message_text="I will improvise instead.", knowledge_ids=(), used_safe_fallback=True),
        context(knowledge_required=True, safe_fallback=safe),
    )
    assert accepted.valid is True
    assert "safe_fallback_text_mismatch" in paraphrased.violations


def test_ordinary_phrase_feel_free_is_not_treated_as_a_free_offer() -> None:
    result = SalesPolicyValidator().validate(
        candidate(message_text="Feel free to tell me what outcome matters most."), context()
    )
    assert result.valid is True


def test_sensitive_price_is_allowed_only_from_referenced_business_fact() -> None:
    grounded = SalesPolicyValidator().validate(
        candidate(message_text="The plan costs $199 per month.", business_fact_ids=("price-1",)),
        context(),
    )
    invented = SalesPolicyValidator().validate(
        candidate(message_text="The plan costs $99 per month."), context()
    )
    assert grounded.valid is True
    assert "ungrounded_sensitive_claim" in invented.violations


@pytest.mark.parametrize(
    "message",
    (
        "Your appointment is confirmed.",
        "You have been booked.",
        "Payment has been processed.",
        "Your discount has been applied.",
    ),
)
def test_generated_text_cannot_execute_commercial_action(message: str) -> None:
    result = SalesPolicyValidator().validate(candidate(message_text=message), context())
    assert "unauthorized_commercial_execution" in result.violations


def test_booking_and_callback_require_verified_capabilities() -> None:
    booking = SalesPolicyValidator().validate(
        candidate(move=SalesMove.OFFER_BOOKING_SLOTS),
        context(approved_move=SalesMove.OFFER_BOOKING_SLOTS, booking_available=False),
    )
    callback = SalesPolicyValidator().validate(
        candidate(move=SalesMove.SCHEDULE_CALLBACK),
        context(approved_move=SalesMove.SCHEDULE_CALLBACK, callback_at=None),
    )
    assert "booking_not_available" in booking.violations
    assert "callback_time_missing" in callback.violations


def test_callback_time_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError):
        context(callback_at=datetime(2026, 9, 7, 15, 0))
    assert context(callback_at=datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc))


def test_stop_suppression_allows_only_exact_server_fallback() -> None:
    safe = "You have been unsubscribed."
    result = SalesPolicyValidator().validate(
        candidate(
            message_text="Maybe reconsider later.",
            move=SalesMove.END_CONTACT,
            knowledge_ids=(),
            customer_evidence_ids=(),
        ),
        context(
            approved_move=SalesMove.END_CONTACT,
            contact_allowed=False,
            safe_fallback=safe,
        ),
    )
    assert "contact_not_allowed" in result.violations
    assert result.message_text == safe


def test_human_takeover_allows_only_exact_server_fallback() -> None:
    result = SalesPolicyValidator().validate(
        candidate(), context(human_takeover_active=True)
    )
    assert "human_takeover_active" in result.violations
