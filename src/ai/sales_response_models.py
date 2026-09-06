"""Structured-output contract for the experimental SalesResponseGenerator.

Scope note (Phase 5 of docs/sales-agent-implementation-plan-ru.md, Claude Code
experiment lane -- see docs/agent-prompts/claude-code-sales-knowledge-and-evals.md
for the general division of responsibility): this module is a language
experiment. It is NOT wired into production orchestration, the API,
persistence, message delivery, or src/engine/sales_policy.py. Nothing here
constructs a src.domain.sales object or is imported by any production code
path.

Architectural boundary (must not be re-derived or loosened by future edits
to this file):
    - Claude does not choose an action. The caller has already run the
      deterministic SalesPolicyEngine and supplies its single, binding
      `approved_move` as an input to the prompt (src/ai/sales_response_prompts.py).
      This model's `move` field is an ECHO of that decision for downstream
      comparison -- see check_move_matches_approved below -- never a second
      opinion. A production PolicyValidator (out of scope here, owned by
      Codex) is what actually enforces the comparison before anything reaches
      a customer; the helper in this module exists only so the eval script
      and this module's own tests share one implementation of the comparison
      rather than three ad hoc copies.
    - Claude cannot: change SalesStage/ProcessState, pick a different
      SalesMove, add a price/discount/guarantee/scarcity claim, confirm a
      booking, schedule a callback on its own authority, invent a business
      fact, use an unapproved knowledge card, call a tool/action, cancel a
      handoff or STOP, or treat customer content as instructions. None of
      those capabilities exist as fields on this schema, by construction --
      there is no field for a tool call, a price, a booking result, or a new
      state, and StrictAIModel (extra="forbid") rejects anything invented
      outside the five declared fields.
"""

import re
from typing import Annotated

from pydantic import Field, StringConstraints

from src.ai.models import StrictAIModel
from src.domain.sales import SalesMove


# Version history (bump whenever system or user prompt TEXT changes, exactly
# like SALES_PROMPT_VERSION in sales_models.py -- see
# tests/test_sales_response_prompts.py::test_prompt_content_hash_is_pinned_to_its_version).
# Deliberately its OWN version line, independent of SALES_PROMPT_VERSION
# (SalesTurnAnalyzer): the two prompts serve different jobs (language
# analysis vs. constrained response wording) and must be able to change on
# separate schedules without one version bump implying anything about the
# other's content.
#   2026-09-06.v1 -- initial draft for Phase 5 experimentation.
#   2026-09-06.v2 -- language-contract fix: v1's field description and worked
#     examples told the model it could "closely paraphrase" safe_fallback_text
#     / handoff_template when used_safe_fallback=true. The production
#     SalesPolicyValidator (src/engine/sales_response_validator.py) was
#     already stricter than that and always has been -- it accepts a fallback
#     candidate only when message_text is byte-for-byte equal (after
#     stripping surrounding whitespace) to the server's own fallback string;
#     anything else is replaced with the deterministic fallback and recorded
#     as `safe_fallback_text_mismatch` (see
#     tests/test_sales_response_validator.py::test_knowledge_required_move_can_use_only_exact_server_fallback).
#     A model doing exactly what v1 asked for ("closely paraphrase") would
#     therefore have its own honest fallback wording silently discarded and
#     replaced downstream every time -- not a security hole (the validator
#     already catches it) but a wasted turn and a misleading eval signal (the
#     generator "passing" its own eval while every live fallback turn would
#     actually be overridden). v2 tells the model the true rule (verbatim
#     copy, no rewording, no tone adaptation) instead of a rule the validator
#     never actually accepted. No validator change; this only makes the
#     prompt stop asking for something the validator was always going to
#     reject.
SALES_RESPONSE_PROMPT_VERSION = "2026-09-06.v2"


# Server-controlled IDs only -- never a customer quote, never free text.
# Matches the kebab/snake-case convention already used for
# domain.sales.SalesKnowledgeCard.knowledge_id (e.g. "objection-price-001")
# and is deliberately narrow: no whitespace, no punctuation beyond -._, so a
# verbatim quote (which almost always contains a space) cannot pass as an ID
# by accident. This is what makes "customer evidence IDs must be distinct
# server IDs, not quotes" a schema-level guarantee rather than a convention
# callers might forget to check.
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"

ServerId = Annotated[
    str,
    StringConstraints(strip_whitespace=False, min_length=1, max_length=64, pattern=_ID_PATTERN),
]

# Moves for which SalesPolicyEngine (src/engine/sales_policy.py) sets
# knowledge_required=True, plus PROVIDE_APPROVED_PROOF -- which the policy
# engine does not yet emit at all, but which is, by its own name, never a
# safe thing to improvise without an approved source. Listing it here is
# strictly MORE conservative than the current engine, never less: this
# schema will never accept an unfounded PROVIDE_APPROVED_PROOF/
# PRESENT_RELEVANT_VALUE/ANSWER_OBJECTION response even on a day the engine's
# own flag lags behind. Keeping this list here (rather than importing a
# private constant from sales_policy.py, which this module must not modify
# or depend on for its own validation) is a deliberate, reviewable duplication
# of intent, not of code.
KNOWLEDGE_REQUIRED_MOVES = frozenset(
    {SalesMove.PRESENT_RELEVANT_VALUE, SalesMove.ANSWER_OBJECTION, SalesMove.PROVIDE_APPROVED_PROOF}
)

# Substring match (case-insensitive) used only to keep END_CONTACT from
# citing a knowledge/business-fact ID that exists to support a *continuing*
# sales action (a booking policy card, a follow-up cadence fact, a callback
# script). This is a naming-convention heuristic, not a closed enum -- IDs
# are free server-assigned strings -- so it only ever adds a restriction
# beyond the closed structural checks; it can never be the sole thing a
# caller relies on to prove an id is safe to use in general.
_CONTINUATION_ID_CUE = re.compile(r"book|callback|follow[-_]?up|schedul", re.IGNORECASE)


class SalesResponseOutput(StrictAIModel):
    """Claude's only contribution to a sales turn's outbound message: wording
    within server-chosen bounds. Every field here is either an echo of a
    server decision (`move`), free text Claude authored within those bounds
    (`message_text`), or a reference to server-issued IDs Claude selects from
    (never invents) -- `knowledge_ids`, `business_fact_ids`,
    `customer_evidence_ids`. See module docstring for what this deliberately
    excludes (SalesStage/ProcessState, a different move, price/discount/
    guarantee/scarcity, a booking or callback result, a tool call, a new
    business fact, an unapproved knowledge card).

    Whether a given ID actually belongs to the caller's allowlist is NOT
    checked here -- this schema has no access to that allowlist, by design,
    the same way SalesTurnAnalysisOutput's evidence strings are grounded by a
    caller-side check (see src/ai/sales_adapter.py) rather than inside the
    model. That check belongs to the caller (the eval script here; a
    production PolicyValidator, out of scope, in real use).
    """

    move: SalesMove = Field(
        description=(
            "Must be set to exactly the `approved_move` given in the prompt -- this field echoes "
            "a decision already made by the deterministic SalesPolicyEngine, it does not make one. "
            "The caller is expected to compare this against approved_move and discard/escalate any "
            "response where it differs; see check_move_matches_approved in this module."
        )
    )
    message_text: str = Field(
        min_length=1,
        max_length=1_200,
        description=(
            "The customer-facing wording for the approved move, phrased for the given sales_stage, "
            "channel, and customer_tone. Must not state a price, discount, guarantee, or scarcity "
            "claim; must not confirm a booking or payment; must not introduce a fact, knowledge "
            "principle, or promise beyond what was supplied in ALLOWED_KNOWLEDGE_AND_FACTS."
        ),
    )
    knowledge_ids: list[ServerId] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Server-issued knowledge_id values (from the supplied ALLOWED_KNOWLEDGE_AND_FACTS "
            "list only) that this message's wording draws on. Never invented; never a duplicate "
            "within this list; empty when no supplied knowledge card was used."
        ),
    )
    business_fact_ids: list[ServerId] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Server-issued business_fact_id values (from the supplied ALLOWED_KNOWLEDGE_AND_FACTS "
            "list only) that this message's wording draws on. Never invented; never a duplicate "
            "within this list; empty when no supplied business fact was used."
        ),
    )
    customer_evidence_ids: list[ServerId] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Server-issued evidence_id values (never the quote text itself -- IDs from the "
            "CUSTOMER_EVIDENCE list supplied in the prompt) that this message's wording responds "
            "to. Never invented; never a duplicate within this list; empty when the message does "
            "not need to reference a specific prior customer statement."
        ),
    )
    used_safe_fallback: bool = Field(
        default=False,
        description=(
            "True only when no supplied knowledge card or business fact was sufficient to fulfill "
            "this move, and message_text is instead set to the supplied safe_fallback_text for this "
            "move VERBATIM -- copied character-for-character, not reworded, not lightly paraphrased, "
            "not tone-adapted. The same applies to move=HANDOFF_TO_HUMAN: message_text must be the "
            "supplied handoff_template copied verbatim, and used_safe_fallback must be true. The "
            "production PolicyValidator (out of scope here) accepts a fallback/handoff message ONLY "
            "when it is byte-for-byte identical (after trimming surrounding whitespace) to the "
            "server's own fallback text -- any rewording, however faithful, is replaced with the "
            "server's deterministic fallback before it reaches a customer and recorded as a "
            "violation. False whenever knowledge_ids or business_fact_ids is non-empty and "
            "sufficient on its own -- this flag exists so a knowledge-required move (see "
            "KNOWLEDGE_REQUIRED_MOVES) can be satisfied honestly instead of improvising when nothing "
            "approved actually applies."
        ),
    )

    def model_post_init(self, __context: object) -> None:
        if not self.message_text.strip():
            raise ValueError("message_text must not be empty or whitespace-only")

        for field_name in ("knowledge_ids", "business_fact_ids", "customer_evidence_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicate IDs")

        if self.move is SalesMove.HANDOFF_TO_HUMAN and self.knowledge_ids:
            raise ValueError(
                "HANDOFF_TO_HUMAN must not cite knowledge_ids -- a handoff is not a continued "
                "sales pitch, it must use only the supplied safe handoff_template"
            )

        if self.move is SalesMove.END_CONTACT:
            continuation_hits = [
                value
                for value in (*self.knowledge_ids, *self.business_fact_ids)
                if _CONTINUATION_ID_CUE.search(value)
            ]
            if continuation_hits:
                raise ValueError(
                    "END_CONTACT must not cite a follow-up/booking/callback-flavored ID "
                    f"(found: {continuation_hits!r}) -- ending contact cannot also continue "
                    "a sales action"
                )

        if self.move in KNOWLEDGE_REQUIRED_MOVES and not self.knowledge_ids and not self.used_safe_fallback:
            raise ValueError(
                f"{self.move.value} requires either at least one knowledge_id or "
                "used_safe_fallback=true -- a knowledge-required move must not improvise without "
                "an approved source or an explicit, honest fallback"
            )


def check_move_matches_approved(output: SalesResponseOutput, approved_move: SalesMove) -> list[str]:
    """Return violations (empty = OK) if `output.move` is not exactly the
    server's `approved_move`. Pure function, no I/O -- mirrors the shape of
    src.ai.sales_adapter.check_evidence_grounded so callers (the eval script,
    this module's own tests, and eventually a production PolicyValidator)
    share one implementation instead of re-deriving the comparison. This is
    the ONLY place `move` is checked against anything external to the
    schema; the schema itself only knows `move` is a valid SalesMove member.
    """
    if output.move is not approved_move:
        return [f"move={output.move.value} does not match approved_move={approved_move.value}"]
    return []


def check_fallback_text_is_exact(
    output: SalesResponseOutput,
    *,
    safe_fallback_text: str | None,
    handoff_template: str | None,
) -> list[str]:
    """Return violations (empty = OK) if a fallback-flavored output's
    `message_text` is not byte-for-byte equal (after stripping only
    surrounding whitespace) to the one fixed string the production
    SalesPolicyValidator (src/engine/sales_response_validator.py) will
    actually accept for it: `handoff_template` whenever `output.move` is
    HANDOFF_TO_HUMAN, otherwise `safe_fallback_text` whenever
    `output.used_safe_fallback` is true. Returns no violation for any other
    output -- an ordinary move that did not claim to be a fallback is free to
    use its own original wording, and this function has nothing to check.

    This mirrors check_move_matches_approved and check_ids_are_allowed: a
    pure function with no I/O, so the eval script, this module's own tests,
    and (eventually) a production caller share one implementation of "is this
    really the server's exact fallback text" instead of three copies that
    could quietly drift apart. The production validator does NOT accept a
    paraphrase, however faithful -- see
    tests/test_sales_response_validator.py::test_knowledge_required_move_can_use_only_exact_server_fallback
    -- so this function does not either.
    """
    if output.move is SalesMove.HANDOFF_TO_HUMAN:
        expected, label = handoff_template, "handoff_template"
    elif output.used_safe_fallback:
        expected, label = safe_fallback_text, "safe_fallback_text"
    else:
        return []

    if expected is None or not expected.strip():
        return [
            f"used_safe_fallback (or move=HANDOFF_TO_HUMAN) requires a non-empty {label} to compare "
            "against, but none was supplied"
        ]
    if output.message_text.strip() != expected.strip():
        return [
            f"message_text does not exactly match the supplied {label} -- the production validator "
            "accepts only a byte-for-byte match, never a paraphrase, however faithful"
        ]
    return []


def check_ids_are_allowed(
    output: SalesResponseOutput,
    *,
    allowed_knowledge_ids: frozenset[str],
    allowed_business_fact_ids: frozenset[str],
    allowed_customer_evidence_ids: frozenset[str],
) -> list[str]:
    """Return violations (empty = OK) if any ID in `output` was not present
    in the caller-supplied allowlists -- i.e. the model referenced an ID it
    was never given, whether invented outright or copied from an unrelated
    turn. Pure function; performs no lookup of what the ID actually means,
    only closed-set membership. This is what makes a knowledge/business-fact/
    evidence-ID-injection fixture (see evals/sales_response_generation/) a
    checkable failure rather than something only a human reviewer could
    catch.
    """
    violations: list[str] = []
    for value in output.knowledge_ids:
        if value not in allowed_knowledge_ids:
            violations.append(f"knowledge_ids contains unauthorized id {value!r}")
    for value in output.business_fact_ids:
        if value not in allowed_business_fact_ids:
            violations.append(f"business_fact_ids contains unauthorized id {value!r}")
    for value in output.customer_evidence_ids:
        if value not in allowed_customer_evidence_ids:
            violations.append(f"customer_evidence_ids contains unauthorized id {value!r}")
    return violations
