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
from .repositories import UnitOfWorkFactory
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
        sweep", exactly like an unmet delay would be."""
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
            delivered = self.sms_service.send_outbound(business_id, to_number=phone, body=response.message_text)

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
                    "message_text": response.message_text,
                    "delivered": delivered,
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
