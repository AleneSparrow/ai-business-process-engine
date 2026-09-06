"""Tests for the experimental SalesResponseGenerator structured-output schema.

Scope: Phase 5 of docs/sales-agent-implementation-plan-ru.md, Claude Code
experimentation lane. Pure unit tests -- no network, no provider, no
SalesPolicyEngine involvement.
"""

import pytest
from pydantic import ValidationError

from src.ai.sales_response_models import (
    KNOWLEDGE_REQUIRED_MOVES,
    SalesResponseOutput,
    check_fallback_text_is_exact,
    check_ids_are_allowed,
    check_move_matches_approved,
)
from src.domain.sales import SalesMove


def _output(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "move": "ANSWER_OBJECTION",
        "message_text": "Is the concern more about the total budget, or whether the result will be worth it?",
        "knowledge_ids": ["objection-price-001"],
        "business_fact_ids": [],
        "customer_evidence_ids": ["ev-1"],
        "used_safe_fallback": False,
    }
    value.update(overrides)
    return value


# ---------------------------------------------------------------------------
# Strict schema: valid case, extra fields, enum values
# ---------------------------------------------------------------------------


def test_valid_output_round_trips() -> None:
    output = SalesResponseOutput.model_validate(_output())
    assert output.move is SalesMove.ANSWER_OBJECTION
    assert output.knowledge_ids == ["objection-price-001"]
    assert output.customer_evidence_ids == ["ev-1"]
    assert output.used_safe_fallback is False


def test_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        SalesResponseOutput.model_validate(_output(price=99))


def test_tool_call_shaped_field_is_rejected() -> None:
    """The schema has no field for a tool call, a booking result, or a new
    process/sales state -- StrictAIModel (extra='forbid') rejects any of
    those the same way it rejects any other invented field."""
    for bad_field in ("tool_call", "booking_result", "process_state", "sales_stage", "price"):
        with pytest.raises(ValidationError):
            SalesResponseOutput.model_validate(_output(**{bad_field: "anything"}))


def test_unknown_move_enum_value_is_rejected_not_coerced() -> None:
    with pytest.raises(ValidationError):
        SalesResponseOutput.model_validate(_output(move="INVENTED_MOVE"))


def test_every_real_sales_move_is_a_valid_move_value() -> None:
    for move in SalesMove:
        # Build a minimally-valid instance per move to make sure the closed
        # enum itself is always accepted (cross-field rules are exercised
        # separately below, this only checks the enum boundary).
        kwargs = _output(move=move.value)
        if move in KNOWLEDGE_REQUIRED_MOVES:
            kwargs["used_safe_fallback"] = True
            kwargs["knowledge_ids"] = []
        if move is SalesMove.HANDOFF_TO_HUMAN:
            kwargs["knowledge_ids"] = []
        if move is SalesMove.END_CONTACT:
            kwargs["knowledge_ids"] = []
            kwargs["business_fact_ids"] = []
        SalesResponseOutput.model_validate(kwargs)


# ---------------------------------------------------------------------------
# Empty / whitespace message_text
# ---------------------------------------------------------------------------


def test_empty_message_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesResponseOutput.model_validate(_output(message_text=""))


def test_whitespace_only_message_text_is_rejected() -> None:
    with pytest.raises(ValidationError, match="empty or whitespace-only"):
        SalesResponseOutput.model_validate(_output(message_text="   \n\t  "))


def test_message_text_over_max_length_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesResponseOutput.model_validate(_output(message_text="x" * 1_201))


# ---------------------------------------------------------------------------
# Duplicate IDs
# ---------------------------------------------------------------------------


def test_duplicate_knowledge_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate IDs"):
        SalesResponseOutput.model_validate(
            _output(knowledge_ids=["objection-price-001", "objection-price-001"])
        )


def test_duplicate_business_fact_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate IDs"):
        SalesResponseOutput.model_validate(
            _output(move="PRESENT_RELEVANT_VALUE", knowledge_ids=[], business_fact_ids=["fact-1", "fact-1"])
        )


def test_duplicate_customer_evidence_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate IDs"):
        SalesResponseOutput.model_validate(_output(customer_evidence_ids=["ev-1", "ev-1"]))


def test_distinct_ids_across_lists_are_not_duplicates() -> None:
    """The same literal string appearing once in each of the three lists is
    not a "duplicate ID" -- dedupe is checked per list, not globally."""
    SalesResponseOutput.model_validate(
        _output(knowledge_ids=["shared-1"], business_fact_ids=["shared-1"], customer_evidence_ids=["shared-1"])
    )


# ---------------------------------------------------------------------------
# ID injection boundary: IDs must be server-issued identifiers, never quotes
# ---------------------------------------------------------------------------


def test_id_containing_a_space_is_rejected() -> None:
    """A verbatim customer quote almost always contains a space -- this is
    the schema-level guarantee that an evidence/knowledge/fact "id" cannot
    actually be a smuggled-in quote."""
    with pytest.raises(ValidationError):
        SalesResponseOutput.model_validate(_output(customer_evidence_ids=["that's way more than expected"]))


def test_id_containing_a_quote_character_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesResponseOutput.model_validate(_output(knowledge_ids=['objection"price']))


def test_empty_string_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesResponseOutput.model_validate(_output(business_fact_ids=[""]))


def test_id_over_max_length_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SalesResponseOutput.model_validate(_output(knowledge_ids=["x" * 65]))


def test_well_formed_kebab_case_id_is_accepted() -> None:
    SalesResponseOutput.model_validate(_output(knowledge_ids=["objection-price-001"]))


# ---------------------------------------------------------------------------
# HANDOFF_TO_HUMAN must not cite knowledge cards
# ---------------------------------------------------------------------------


def test_handoff_to_human_with_knowledge_ids_is_rejected() -> None:
    with pytest.raises(ValidationError, match="HANDOFF_TO_HUMAN must not cite knowledge_ids"):
        SalesResponseOutput.model_validate(
            _output(
                move="HANDOFF_TO_HUMAN",
                message_text="A team member will follow up shortly.",
                knowledge_ids=["objection-price-001"],
                used_safe_fallback=True,
            )
        )


def test_handoff_to_human_without_knowledge_ids_is_accepted() -> None:
    SalesResponseOutput.model_validate(
        _output(
            move="HANDOFF_TO_HUMAN",
            message_text="A team member will follow up shortly.",
            knowledge_ids=[],
            used_safe_fallback=True,
        )
    )


def test_handoff_to_human_may_still_cite_business_facts() -> None:
    """Only knowledge_ids are restricted for HANDOFF_TO_HUMAN -- a business
    fact (e.g. a contact channel) is not "continuing the sales pitch" the
    way a knowledge card's methodology would be."""
    SalesResponseOutput.model_validate(
        _output(
            move="HANDOFF_TO_HUMAN",
            message_text="A team member will follow up shortly.",
            knowledge_ids=[],
            business_fact_ids=["support-hours-001"],
            used_safe_fallback=True,
        )
    )


# ---------------------------------------------------------------------------
# END_CONTACT must not carry a follow-up/booking-flavored id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flavored_id",
    ["booking-policy-001", "follow-up-cadence-001", "followup-cadence-001", "callback-script-001", "schedule-001"],
)
def test_end_contact_with_a_continuation_flavored_business_fact_id_is_rejected(flavored_id: str) -> None:
    with pytest.raises(ValidationError, match="must not cite a follow-up/booking/callback-flavored ID"):
        SalesResponseOutput.model_validate(
            _output(
                move="END_CONTACT",
                message_text="Thanks for your time, take care.",
                knowledge_ids=[],
                business_fact_ids=[flavored_id],
            )
        )


def test_end_contact_with_a_continuation_flavored_knowledge_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not cite a follow-up/booking/callback-flavored ID"):
        SalesResponseOutput.model_validate(
            _output(
                move="END_CONTACT",
                message_text="Thanks for your time, take care.",
                knowledge_ids=["booking-policy-001"],
                business_fact_ids=[],
            )
        )


def test_end_contact_with_an_unrelated_id_is_accepted() -> None:
    SalesResponseOutput.model_validate(
        _output(
            move="END_CONTACT",
            message_text="Thanks for your time, take care.",
            knowledge_ids=[],
            business_fact_ids=["service-desc-001"],
        )
    )


def test_end_contact_with_no_ids_is_accepted() -> None:
    SalesResponseOutput.model_validate(
        _output(move="END_CONTACT", message_text="Thanks for your time, take care.", knowledge_ids=[], business_fact_ids=[])
    )


# ---------------------------------------------------------------------------
# Knowledge-required moves: knowledge_ids or an explicit safe fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("move", sorted(m.value for m in KNOWLEDGE_REQUIRED_MOVES))
def test_knowledge_required_move_without_knowledge_or_fallback_is_rejected(move: str) -> None:
    with pytest.raises(ValidationError, match="requires either at least one knowledge_id or"):
        SalesResponseOutput.model_validate(
            _output(move=move, message_text="Here is some wording.", knowledge_ids=[], used_safe_fallback=False)
        )


@pytest.mark.parametrize("move", sorted(m.value for m in KNOWLEDGE_REQUIRED_MOVES))
def test_knowledge_required_move_with_knowledge_ids_is_accepted(move: str) -> None:
    SalesResponseOutput.model_validate(
        _output(move=move, message_text="Here is some wording.", knowledge_ids=["k-1"], used_safe_fallback=False)
    )


@pytest.mark.parametrize("move", sorted(m.value for m in KNOWLEDGE_REQUIRED_MOVES))
def test_knowledge_required_move_with_safe_fallback_and_no_knowledge_is_accepted(move: str) -> None:
    SalesResponseOutput.model_validate(
        _output(move=move, message_text="Here is some wording.", knowledge_ids=[], used_safe_fallback=True)
    )


def test_non_knowledge_required_move_needs_neither() -> None:
    SalesResponseOutput.model_validate(
        _output(
            move="ASK_DISCOVERY_QUESTION",
            message_text="What's the main thing you're trying to solve?",
            knowledge_ids=[],
            business_fact_ids=[],
            customer_evidence_ids=[],
            used_safe_fallback=False,
        )
    )


# ---------------------------------------------------------------------------
# check_move_matches_approved
# ---------------------------------------------------------------------------


def test_check_move_matches_approved_accepts_a_matching_move() -> None:
    output = SalesResponseOutput.model_validate(_output())
    assert check_move_matches_approved(output, SalesMove.ANSWER_OBJECTION) == []


def test_check_move_matches_approved_rejects_a_mismatched_move() -> None:
    output = SalesResponseOutput.model_validate(_output())
    violations = check_move_matches_approved(output, SalesMove.OFFER_BOOKING_SLOTS)
    assert len(violations) == 1
    assert "does not match approved_move" in violations[0]


# ---------------------------------------------------------------------------
# check_ids_are_allowed
# ---------------------------------------------------------------------------


def test_check_ids_are_allowed_accepts_ids_within_every_allowlist() -> None:
    output = SalesResponseOutput.model_validate(_output())
    violations = check_ids_are_allowed(
        output,
        allowed_knowledge_ids=frozenset({"objection-price-001"}),
        allowed_business_fact_ids=frozenset(),
        allowed_customer_evidence_ids=frozenset({"ev-1"}),
    )
    assert violations == []


def test_check_ids_are_allowed_flags_an_unauthorized_knowledge_id() -> None:
    output = SalesResponseOutput.model_validate(_output(knowledge_ids=["unlimited-discount-001"]))
    violations = check_ids_are_allowed(
        output,
        allowed_knowledge_ids=frozenset({"objection-price-001"}),
        allowed_business_fact_ids=frozenset(),
        allowed_customer_evidence_ids=frozenset({"ev-1"}),
    )
    assert any("unlimited-discount-001" in v for v in violations)


def test_check_ids_are_allowed_flags_an_unauthorized_business_fact_id() -> None:
    output = SalesResponseOutput.model_validate(
        _output(
            move="PRESENT_RELEVANT_VALUE",
            knowledge_ids=[],
            business_fact_ids=["core-pricing-tier-001"],
            used_safe_fallback=True,
        )
    )
    violations = check_ids_are_allowed(
        output,
        allowed_knowledge_ids=frozenset(),
        allowed_business_fact_ids=frozenset({"service-desc-001"}),
        allowed_customer_evidence_ids=frozenset(),
    )
    assert any("core-pricing-tier-001" in v for v in violations)


def test_check_ids_are_allowed_flags_an_unauthorized_evidence_id() -> None:
    output = SalesResponseOutput.model_validate(_output(customer_evidence_ids=["ev-999"]))
    violations = check_ids_are_allowed(
        output,
        allowed_knowledge_ids=frozenset({"objection-price-001"}),
        allowed_business_fact_ids=frozenset(),
        allowed_customer_evidence_ids=frozenset({"ev-1"}),
    )
    assert any("ev-999" in v for v in violations)


# ---------------------------------------------------------------------------
# check_fallback_text_is_exact -- must match src.engine.sales_response_validator's
# byte-for-byte rule, never accept a paraphrase (see
# tests/test_sales_response_validator.py::test_knowledge_required_move_can_use_only_exact_server_fallback
# for the production-side version of this same rule).
# ---------------------------------------------------------------------------


def test_fallback_check_passes_an_exact_safe_fallback_match() -> None:
    output = SalesResponseOutput.model_validate(
        _output(
            move="ANSWER_OBJECTION",
            message_text="I hear you -- can you tell me more about that?",
            knowledge_ids=[],
            used_safe_fallback=True,
        )
    )
    violations = check_fallback_text_is_exact(
        output,
        safe_fallback_text="I hear you -- can you tell me more about that?",
        handoff_template=None,
    )
    assert violations == []


def test_fallback_check_tolerates_only_surrounding_whitespace() -> None:
    output = SalesResponseOutput.model_validate(
        _output(
            move="ANSWER_OBJECTION",
            message_text="  I hear you -- can you tell me more about that?  ",
            knowledge_ids=[],
            used_safe_fallback=True,
        )
    )
    violations = check_fallback_text_is_exact(
        output,
        safe_fallback_text="I hear you -- can you tell me more about that?",
        handoff_template=None,
    )
    assert violations == []


def test_fallback_check_rejects_a_faithful_paraphrase() -> None:
    output = SalesResponseOutput.model_validate(
        _output(
            move="ANSWER_OBJECTION",
            message_text="I understand -- could you share a bit more about that?",
            knowledge_ids=[],
            used_safe_fallback=True,
        )
    )
    violations = check_fallback_text_is_exact(
        output,
        safe_fallback_text="I hear you -- can you tell me more about that?",
        handoff_template=None,
    )
    assert len(violations) == 1
    assert "does not exactly match" in violations[0]


def test_fallback_check_rejects_a_shortened_fallback() -> None:
    output = SalesResponseOutput.model_validate(
        _output(
            move="ANSWER_OBJECTION",
            message_text="I hear you.",
            knowledge_ids=[],
            used_safe_fallback=True,
        )
    )
    violations = check_fallback_text_is_exact(
        output, safe_fallback_text="I hear you -- can you tell me more about that?", handoff_template=None
    )
    assert violations


def test_fallback_check_requires_a_supplied_safe_fallback_text() -> None:
    output = SalesResponseOutput.model_validate(
        _output(move="ANSWER_OBJECTION", message_text="Something.", knowledge_ids=[], used_safe_fallback=True)
    )
    violations = check_fallback_text_is_exact(output, safe_fallback_text=None, handoff_template=None)
    assert violations
    assert "requires a non-empty safe_fallback_text" in violations[0]


def test_fallback_check_passes_an_exact_handoff_template_match() -> None:
    output = SalesResponseOutput.model_validate(
        _output(
            move="HANDOFF_TO_HUMAN",
            message_text="A team member will follow up shortly.",
            knowledge_ids=[],
            used_safe_fallback=True,
        )
    )
    violations = check_fallback_text_is_exact(
        output, safe_fallback_text=None, handoff_template="A team member will follow up shortly."
    )
    assert violations == []


def test_fallback_check_rejects_a_reworded_handoff_template() -> None:
    output = SalesResponseOutput.model_validate(
        _output(
            move="HANDOFF_TO_HUMAN",
            message_text="Someone from our team will reach out to you soon.",
            knowledge_ids=[],
            used_safe_fallback=True,
        )
    )
    violations = check_fallback_text_is_exact(
        output, safe_fallback_text=None, handoff_template="A team member will follow up shortly."
    )
    assert violations
    assert "handoff_template" in violations[0]


def test_fallback_check_uses_handoff_template_even_if_a_safe_fallback_text_is_also_supplied() -> None:
    """HANDOFF_TO_HUMAN always compares against handoff_template, never
    safe_fallback_text, regardless of what else the caller happens to pass --
    mirrors the production validator, which is handed a single fallback
    string per turn by its caller and never asked to pick between two."""
    output = SalesResponseOutput.model_validate(
        _output(
            move="HANDOFF_TO_HUMAN",
            message_text="A team member will follow up shortly.",
            knowledge_ids=[],
            used_safe_fallback=True,
        )
    )
    violations = check_fallback_text_is_exact(
        output,
        safe_fallback_text="Thanks for sharing that. A team member can help with the next step.",
        handoff_template="A team member will follow up shortly.",
    )
    assert violations == []


def test_fallback_check_does_not_accept_safe_fallback_text_in_place_of_handoff_template() -> None:
    """The inverse of the test above: copying safe_fallback_text when the
    move is HANDOFF_TO_HUMAN is still a mismatch, even if that string is
    itself a plausible handoff."""
    output = SalesResponseOutput.model_validate(
        _output(
            move="HANDOFF_TO_HUMAN",
            message_text="Thanks for sharing that. A team member can help with the next step.",
            knowledge_ids=[],
            used_safe_fallback=True,
        )
    )
    violations = check_fallback_text_is_exact(
        output,
        safe_fallback_text="Thanks for sharing that. A team member can help with the next step.",
        handoff_template="A team member will follow up shortly.",
    )
    assert violations
    assert "handoff_template" in violations[0]


def test_fallback_check_ignores_a_non_fallback_ordinary_output() -> None:
    """A move that never claimed used_safe_fallback and is not HANDOFF_TO_HUMAN
    is free to write its own original wording -- nothing to compare here."""
    output = SalesResponseOutput.model_validate(_output(used_safe_fallback=False))
    violations = check_fallback_text_is_exact(
        output, safe_fallback_text="completely unrelated fallback text", handoff_template=None
    )
    assert violations == []


def test_check_ids_are_allowed_is_a_pure_function_with_no_lookup_of_meaning() -> None:
    """Membership only -- it does not care whether the id "makes sense" for
    the move, only whether it was in the set the caller supplied."""
    output = SalesResponseOutput.model_validate(_output(knowledge_ids=["totally-unrelated-999"]))
    violations = check_ids_are_allowed(
        output,
        allowed_knowledge_ids=frozenset({"totally-unrelated-999"}),
        allowed_business_fact_ids=frozenset(),
        allowed_customer_evidence_ids=frozenset({"ev-1"}),
    )
    assert violations == []
