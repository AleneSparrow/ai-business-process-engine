"""Proactive stalled-lead re-contact (universal-sales-cycle-model.md section 8).

Distinct from `ProcessState.FOLLOW_UP` (a state used elsewhere, in
`commercial_service.py`, for POST-commercial follow-up -- payment/review
nudges after a booking or accepted quote). This module recovers a sale that
went quiet: mid-qualification, after a slot offer (`QUALIFIED`), or after a
quote that was not accepted (`QUOTED`). It never changes `case.current_state`
-- a sent follow-up is recorded purely as a `FOLLOW_UP_SENT` event plus a
`case.metadata["follow_up"]` attempt counter, the same bookkeeping pattern
`LeadIntakeService` already uses for `MAX_REASSURANCE_ATTEMPTS`.

It is not a CRM check-in. Copy comes from `sales_playbook`: restate the
outstanding question or re-ask for the commitment already on the table.

Everything here is dependency-free and pure (no DB, no AI provider, no
datetime.now() call) so it's fully unit-testable -- the DB scan and the
actual SMS send live in `src/persistence/follow_up_service.py`.

Gating, all of which must hold before a follow-up is ever considered due:

- `case.lead.sms_consent` is True -- a deliberate UI opt-in, never inferred
  by the AI (see Lead.sms_consent). No consent, no follow-up, ever.
- `case.lead.phone` is set -- nothing to text otherwise.
- `case.current_state` is one of the stalled sales states (NEW_LEAD,
  CONTACTED, QUALIFYING, QUALIFIED, QUOTED) -- NOT NEEDS_HUMAN (a human is
  already expected to be handling it) and not BOOKED/WON/LOST/CANCELLED.
- The business has configured `sales.follow_up` (delays_hours,
  maximum_attempts) -- if missing or malformed, treated as "not configured",
  never as an error that could crash a sweep over other businesses' cases.
- Fewer than `maximum_attempts` follow-ups already sent for this case.
- Enough time has passed since the case's last activity (the later of its
  last inbound customer message and its last follow-up already sent) --
  `delays_hours[attempts_sent]` hours.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Protocol

from src.domain.events import EventType
from src.domain.models import ProcessCase
from src.domain.qualification import CustomerResponse, MissingInformationResult
from src.domain.states import ProcessState
from src.engine.sales_playbook import nurture_copy

STALLED_STATES = frozenset({
    ProcessState.NEW_LEAD,
    ProcessState.CONTACTED,
    ProcessState.QUALIFYING,
    ProcessState.QUALIFIED,
    ProcessState.QUOTED,
})


@dataclass(frozen=True, slots=True)
class FollowUpDecision:
    due: bool
    # 1-indexed for human-readable logging/events ("this is attempt 2 of 3");
    # None when not due.
    attempt_number: int | None = None
    reason: str = ""


def decide_follow_up(
    case: ProcessCase,
    business_dna: Mapping[str, object],
    now: datetime,
) -> FollowUpDecision:
    if not case.lead.sms_consent:
        return FollowUpDecision(False, reason="no_sms_consent")
    if not case.lead.phone:
        return FollowUpDecision(False, reason="no_phone")
    if case.current_state not in STALLED_STATES:
        return FollowUpDecision(False, reason="case_not_in_stalled_state")

    config = _follow_up_config(business_dna)
    if config is None:
        return FollowUpDecision(False, reason="follow_up_not_configured")
    delays_hours, maximum_attempts = config

    attempts_sent = _attempts_sent(case)
    if attempts_sent >= maximum_attempts:
        return FollowUpDecision(False, reason="max_attempts_reached")
    if attempts_sent >= len(delays_hours):
        return FollowUpDecision(False, reason="no_configured_delay_for_this_attempt")

    last_activity_at = _last_activity_at(case)
    if last_activity_at is None:
        return FollowUpDecision(False, reason="no_recorded_activity")

    due_at = last_activity_at + timedelta(hours=delays_hours[attempts_sent])
    if now < due_at:
        return FollowUpDecision(False, reason="delay_not_elapsed")

    return FollowUpDecision(True, attempt_number=attempts_sent + 1, reason="due")


def record_follow_up_sent(case: ProcessCase) -> None:
    """Mutates `case.metadata` in place -- call only after the SMS send has
    actually been attempted (see PersistentFollowUpRunner). Sticky/monotonic:
    only ever increments, mirroring how `reassurance_attempts` is tracked in
    LeadIntakeService."""
    case.metadata["follow_up_attempts_sent"] = _attempts_sent(case) + 1


def _attempts_sent(case: ProcessCase) -> int:
    value = case.metadata.get("follow_up_attempts_sent", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _follow_up_config(business_dna: Mapping[str, object]) -> tuple[tuple[int, ...], int] | None:
    sales = business_dna.get("sales")
    if not isinstance(sales, Mapping):
        return None
    follow_up = sales.get("follow_up")
    if not isinstance(follow_up, Mapping):
        return None
    delays = follow_up.get("delays_hours")
    maximum_attempts = follow_up.get("maximum_attempts")
    # (list, tuple), not just list: BusinessDNAVersion freezes its whole
    # configuration (see domain/models._freeze) -- every business_dna that
    # actually reaches this function through the persistence layer
    # (BusinessDNARepository.get_active, what PersistentFollowUpRunner uses)
    # has already had delays_hours converted from a JSON list into a tuple.
    # Requiring `list` here rejected every real, persisted business_dna --
    # found via tests/test_follow_up_service.py, which is the first test to
    # exercise this against an actual persisted (frozen) configuration
    # rather than a hand-built plain dict.
    if not isinstance(delays, (list, tuple)) or not delays:
        return None
    if not all(isinstance(item, int) and item > 0 for item in delays):
        return None
    if not isinstance(maximum_attempts, int) or maximum_attempts <= 0:
        return None
    return tuple(delays), maximum_attempts


def missing_information_from_case(case: ProcessCase) -> MissingInformationResult:
    """Reconstructs "what's still outstanding" from the case's own event
    history rather than re-running QualificationService (which needs a live
    IntentResult from an actual incoming message -- there isn't one here,
    the case has gone quiet). The most recent QUALIFICATION_EVALUATED event
    already recorded exactly this, computed by the real reactive flow, so
    reusing it is both simpler and more accurate than reconstructing it."""
    for event in reversed(case.event_history):
        if event.event_type == EventType.QUALIFICATION_EVALUATED:
            payload = event.payload
            missing_fields = payload.get("missing_fields", ())
            unanswered_questions = payload.get("unanswered_questions", ())
            return MissingInformationResult(
                tuple(missing_fields) if isinstance(missing_fields, (list, tuple)) else (),
                tuple(unanswered_questions) if isinstance(unanswered_questions, (list, tuple)) else (),
            )
    return MissingInformationResult()


def _last_activity_at(case: ProcessCase) -> datetime | None:
    timestamps = [
        event.occurred_at
        for event in case.event_history
        if event.event_type in (EventType.LEAD_INTAKE_RECEIVED, EventType.FOLLOW_UP_SENT)
    ]
    return max(timestamps) if timestamps else None


class FollowUpMessageGenerator(Protocol):
    def generate(
        self,
        missing: MissingInformationResult,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        attempt_number: int,
        current_state: ProcessState | None = None,
    ) -> CustomerResponse: ...


class DeterministicFollowUpMessageGenerator:
    """Always-available fallback. Never invents urgency, discounts, or
    promises — restates outstanding questions, or the sales-playbook close
    already on the table."""

    def generate(
        self,
        missing: MissingInformationResult,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        attempt_number: int,
        current_state: ProcessState | None = None,
    ) -> CustomerResponse:
        business = business_dna.get("business", {})
        name = business.get("name") if isinstance(business, Mapping) else None
        greeting = f"Hi, this is {name.strip()}. " if isinstance(name, str) and name.strip() else "Hi -- "
        close = nurture_copy(current_state or ProcessState.QUALIFYING, missing_complete=missing.complete)
        if close:
            text = greeting + close
        else:
            customer_information = business_dna.get("customer_information", {})
            field_questions = (
                customer_information.get("field_questions", {})
                if isinstance(customer_information, Mapping)
                else {}
            )
            prompts: list[str] = []
            for field_name in missing.missing_fields:
                prompt = field_questions.get(field_name) if isinstance(field_questions, Mapping) else None
                if isinstance(prompt, str) and prompt.strip():
                    prompts.append(prompt.strip())
            prompts.extend(question.strip() for question in missing.unanswered_questions)
            body = " ".join(prompts) if prompts else nurture_copy(
                ProcessState.QUALIFYING, missing_complete=True
            )
            text = f"{greeting}just following up on your request -- {body}"
        return CustomerResponse(
            message_text=text,
            channel=channel,
            reason="follow_up",
            related_case_id=case_id,
        )
