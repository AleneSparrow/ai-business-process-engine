"""Persisted proactive follow-up sweep (universal-sales-cycle-model.md
section 8) -- the DB/SMS orchestration around the pure decision logic in
`src/engine/follow_up.py`.

Deliberately NOT an in-process background thread/loop. This is invoked from
outside the request path -- either a manually-called internal API endpoint
(see `src/api/routes/internal.py`) or that same endpoint hit on a schedule
by a Railway Cron Job (Alena's choice, made after the deploy). Two reasons
for that split rather than a `while True: sleep(...)` task started at
FastAPI startup:

1. If the web service ever runs more than one replica, an in-process loop
   runs once PER replica with no coordination -- every replica would try to
   follow up on the same stalled case at the same tick. An externally
   triggered sweep is a single call site the operator controls the cadence
   of.
2. Per-case optimistic concurrency (`ProcessCaseRepository.save`'s
   `expected_version` check) still protects against the residual case of
   two overlapping sweeps racing on the very same case: whichever commits
   second gets `StaleCaseError`, is caught here, and simply skips that case
   for this sweep -- it's picked up again (or found no-longer-due, if the
   other sweep already sent it) on the next one. This is what makes running
   the sweep from more than one place at once safe rather than merely
   unlikely to collide.
"""

import json
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.domain.events import EventType
from src.domain.models import ProcessEvent
from src.domain.states import ProcessState
from src.engine.follow_up import (
    DeterministicFollowUpMessageGenerator,
    FollowUpMessageGenerator,
    decide_follow_up,
    missing_information_from_case,
    record_follow_up_sent,
)

from .errors import StaleCaseError
from .repositories import DeliveryStatus, UnitOfWorkFactory
from .sms_service import SmsService

LOGGER = logging.getLogger("uvicorn.error")

# Cases in any other state have either resolved (QUALIFIED and later) or
# are already NEEDS_HUMAN, where a human -- not an automated nudge -- is
# expected to be the next thing the customer hears from. See
# src/engine/follow_up.py's STALLED_STATES, kept in sync with this.
_STALLED_STATES = (ProcessState.NEW_LEAD, ProcessState.CONTACTED, ProcessState.QUALIFYING)


def _log_event(level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: value for key, value in fields.items() if value is not None}}
    LOGGER.log(level, json.dumps(payload, separators=(",", ":"), default=str))


@dataclass(frozen=True, slots=True)
class FollowUpSweepResult:
    businesses_scanned: int
    cases_considered: int
    follow_ups_sent: int
    follow_ups_skipped_stale: int


class PersistentFollowUpRunner:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        sms_service: SmsService,
        message_generator: FollowUpMessageGenerator | None = None,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.sms_service = sms_service
        self.message_generator = message_generator or DeterministicFollowUpMessageGenerator()

    def run(self, now: datetime) -> FollowUpSweepResult:
        with self.unit_of_work_factory() as uow:
            businesses = uow.businesses.list_all()
        cases_considered = 0
        follow_ups_sent = 0
        follow_ups_skipped_stale = 0
        for business in businesses:
            sent, considered, skipped = self._sweep_business(business.business_id, now)
            cases_considered += considered
            follow_ups_sent += sent
            follow_ups_skipped_stale += skipped
        _log_event(
            logging.INFO,
            "follow_up_sweep_completed",
            businesses_scanned=len(businesses),
            cases_considered=cases_considered,
            follow_ups_sent=follow_ups_sent,
            follow_ups_skipped_stale=follow_ups_skipped_stale,
        )
        return FollowUpSweepResult(len(businesses), cases_considered, follow_ups_sent, follow_ups_skipped_stale)

    def _sweep_business(self, business_id: str, now: datetime) -> tuple[int, int, int]:
        with self.unit_of_work_factory() as uow:
            dna_version = uow.business_dna.get_active(business_id)
            if dna_version is None:
                return 0, 0, 0
            business_dna = dna_version.configuration
            # No provisioned number -- nothing here can ever be sent, so
            # skip scanning this business's cases entirely rather than
            # deciding "due" on every sweep and never actually delivering.
            if not self.sms_service.configured or self.sms_service.get_number(business_id) is None:
                return 0, 0, 0
            # Oldest-updated-first and pre-filtered to the stalled states in
            # SQL -- see ProcessCaseRepository.list_by_state's docstring for
            # why list_for_business (most-recent-first) would be wrong here.
            cases = uow.cases.list_by_state(business_id, _STALLED_STATES)

        sent = 0
        considered = 0
        skipped_stale = 0
        for case in cases:
            considered += 1
            decision = decide_follow_up(case, business_dna, now)
            if not decision.due:
                continue
            outcome = self._send_one(business_id, case.case_id, now)
            if outcome == "sent":
                sent += 1
            elif outcome == "stale":
                skipped_stale += 1
        return sent, considered, skipped_stale

    def _send_one(self, business_id: str, case_id: str, now: datetime) -> str:
        """Re-reads and re-decides against a fresh copy of the case inside
        its own transaction -- the outer scan's copy may be stale by the
        time we get here (the customer replied, another sweep already sent
        this one, an escalation fired). Never raises: StaleCaseError from
        the version-conflict race is caught and treated as "try again next
        sweep", exactly like an unmet delay would be.

        Durable-outbox delivery, in three separate transactions rather than
        "send, then hope the one DB write after it succeeds":

        1. Atomically claim the (business_id, case_id, attempt_number)
           delivery-attempt row -- the outbox "intent" -- *before* Twilio is
           ever called. The unique key on that row is what makes this safe
           to re-enter: a retried sweep for the same attempt gets back the
           same row instead of creating a second one.
        2. Re-check deterministic policy under a case-row lock, then call
           Twilio and record the outcome (SID or failure) on that same row.
        3. Only then update the case (FOLLOW_UP_SENT event, attempt count).

        Twilio's Messages API has no client-supplied idempotency key, so
        exact-once isn't achievable end-to-end. What this buys over the
        previous send-then-persist ordering is a much narrower duplicate
        window: today, ANY failure in step 3 (for any reason, on any future
        sweep) resent the SMS, indefinitely. With the attempt row claimed
        first, the only way to still get a duplicate is a crash strictly
        between Twilio confirming dispatch and this process persisting that
        confirmation in step 2 -- and even then, at most one extra send,
        never a repeat on every later sweep. That's the documented
        at-least-once behavior the task calls for when exact-once isn't
        available."""
        with self.unit_of_work_factory() as uow:
            case = uow.cases.get(business_id, case_id)
            if case is None:
                return "gone"
            dna_version = uow.business_dna.get_active(business_id)
            if dna_version is None:
                return "gone"
            business_dna = dna_version.configuration
            decision = decide_follow_up(case, business_dna, now)
            if not decision.due:
                return "no_longer_due"
            phone = case.lead.phone
            if not phone:
                return "no_longer_due"

            missing = missing_information_from_case(case)
            response = self.message_generator.generate(
                missing, business_dna, "sms", case.case_id, attempt_number=decision.attempt_number,
            )
            attempt, owns_send = uow.follow_up_deliveries.claim_attempt(
                business_id, case_id, decision.attempt_number,
                message_text=response.message_text, now=now,
            )
            uow.commit()

        if not owns_send:
            if attempt.status == DeliveryStatus.SENT:
                # Resuming after a crash between Twilio confirming dispatch
                # and this process recording it below -- the SMS already
                # went out (twilio_sid is that proof). Do not send it
                # again; just finish updating the case.
                delivered, twilio_sid = True, attempt.twilio_sid
            elif attempt.status == DeliveryStatus.FAILED:
                # A previous attempt at this exact delivery already failed
                # and was recorded as such -- nothing new to send; finish
                # the case update with the same outcome so the attempt is
                # still consumed.
                delivered, twilio_sid = False, None
            else:
                # Someone else (a concurrent sweep, most likely) claimed
                # this attempt and hasn't recorded an outcome yet. Sending
                # here too would risk a duplicate -- back off and let the
                # owner finish; this case is picked up again next sweep.
                return "already_claimed"
        else:
            dispatched = self._authorize_and_dispatch(
                business_id,
                case_id,
                decision.attempt_number,
                now,
                attempt.message_text,
            )
            if dispatched is None:
                # The claim remains durable, but is deliberately not marked
                # sent/failed: no provider call occurred and no follow-up was
                # authorized. A future sweep must re-evaluate policy first.
                return "no_longer_due"
            delivered, twilio_sid = dispatched

        return self._record_outcome_if_still_due(
            business_id,
            case_id,
            decision.attempt_number,
            now,
            attempt.message_text,
            delivered,
            twilio_sid,
        )

    def _authorize_and_dispatch(
        self,
        business_id: str,
        case_id: str,
        attempt_number: int,
        now: datetime,
        message_text: str,
    ) -> tuple[bool, str | None] | None:
        """Re-check policy while holding the case row lock through dispatch.

        A customer response, escalation, takeover, or state transition that
        committed before this lock is acquired makes the pending delivery a
        no-op. A competing case writer that arrives later waits until the
        SMS outcome has been durably recorded, so the message was authorized
        at the actual send point rather than only when the sweep scanned it.
        """
        with self.unit_of_work_factory() as uow:
            case = uow.cases.get(business_id, case_id, for_update=True)
            if case is None:
                return None
            dna_version = uow.business_dna.get_active(business_id)
            if dna_version is None:
                return None
            decision = decide_follow_up(case, dna_version.configuration, now)
            if not decision.due or decision.attempt_number != attempt_number or not case.lead.phone:
                return None
            if self.sms_service.is_suppressed(business_id, case.lead.phone):
                return None
            twilio_sid = self.sms_service.send_outbound(
                business_id, to_number=case.lead.phone, body=message_text
            )
            delivered = twilio_sid is not None
            uow.follow_up_deliveries.mark_result(
                business_id, case_id, attempt_number,
                sent=delivered, twilio_sid=twilio_sid, now=now,
            )
            uow.commit()
            return delivered, twilio_sid

    def _record_outcome_if_still_due(
        self,
        business_id: str,
        case_id: str,
        attempt_number: int,
        now: datetime,
        message_text: str,
        delivered: bool,
        twilio_sid: str | None,
    ) -> str:
        with self.unit_of_work_factory() as uow:
            case = uow.cases.get(business_id, case_id)
            if case is None:
                return "gone"
            dna_version = uow.business_dna.get_active(business_id)
            if dna_version is None:
                return "gone"
            decision = decide_follow_up(case, dna_version.configuration, now)
            if not decision.due or decision.attempt_number != attempt_number:
                # The provider outcome is durable, but never fabricate a
                # FOLLOW_UP_SENT audit event for a case whose policy changed.
                return "no_longer_due"
            expected_version = case.version
            existing_event_count = len(case.event_history)
            # An attempt is consumed regardless of delivery outcome (same
            # philosophy as MAX_REASSURANCE_ATTEMPTS): a failed Twilio send
            # still advances the "last activity" clock, so a persistently
            # failing number is retried on the next configured delay rather
            # than hammered every sweep tick.
            record_follow_up_sent(case)
            case.record(ProcessEvent(
                EventType.FOLLOW_UP_SENT,
                occurred_at=now,
                source="follow_up_runner",
                payload={
                    "attempt_number": decision.attempt_number,
                    "message_fingerprint": hashlib.sha256(message_text.encode("utf-8")).hexdigest(),
                    "delivered": delivered,
                    "twilio_sid": twilio_sid,
                },
            ))
            try:
                uow.cases.save(case, expected_version)
            except StaleCaseError:
                return "stale"
            new_events = case.event_history[existing_event_count:]
            uow.events.add_many(business_id, case.case_id, new_events)
            uow.commit()
            _log_event(
                logging.INFO,
                "follow_up_sent",
                business_id=business_id,
                case_id=case_id,
                attempt_number=decision.attempt_number,
                delivered=delivered,
            )
            return "sent"
