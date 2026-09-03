"""Move a prospect through attract / loyalty until they inquire, then hand off."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping

from src.demand.domain.consent import ConsentAction, ConsentChannel, ConsentRecord
from src.demand.domain.events import ProspectEventType
from src.demand.domain.handoff import InquiryHandoff
from src.demand.domain.models import Campaign, OutboundMessage, Prospect, ProspectEvent, SequenceStep
from src.demand.domain.state_machine import InvalidDemandTransition, ProspectStateMachine
from src.demand.domain.states import CampaignState, ProspectState
from src.demand.engine.claim_guard import assert_claims_allowed, assert_publishable
from src.demand.engine.consent_gate import ConsentRequiredError, assert_can_send
from src.demand.engine.sequence_planner import compile_welcome_sequence, render_step
from src.demand.engine.strategy_service import require_live
from src.demand.domain.primitives import utc_now


_STATE_RANK = {
    ProspectState.UNKNOWN: 0,
    ProspectState.AWARE: 1,
    ProspectState.ENGAGED: 2,
    ProspectState.SUBSCRIBED: 3,
    ProspectState.NURTURING: 4,
    ProspectState.INTENT: 5,
    ProspectState.INQUIRED: 6,
    ProspectState.HANDED_OFF: 7,
}

_POINTS = {
    ProspectEventType.CONTENT_VIEWED: 5,
    ProspectEventType.CONTENT_ENGAGED: 15,
    ProspectEventType.OPT_IN_RECORDED: 25,
    ProspectEventType.SEQUENCE_STEP_OPENED: 5,
    ProspectEventType.CTA_CLICKED: 20,
    ProspectEventType.INQUIRY_RECEIVED: 50,
}


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    prospect: Prospect
    state: ProspectState
    handoff: InquiryHandoff | None = None
    outbound: OutboundMessage | None = None
    blocked_reason: str | None = None


class AcquisitionEngine:
    def __init__(self, state_machine: ProspectStateMachine | None = None) -> None:
        self.state_machine = state_machine or ProspectStateMachine()

    def receive(
        self,
        campaign: Campaign,
        prospect: Prospect,
        event: ProspectEvent,
    ) -> AcquisitionResult:
        require_live(campaign)
        if prospect.business_id != campaign.business_id or prospect.campaign_id != campaign.campaign_id:
            raise ValueError("prospect does not belong to this campaign")
        if prospect.has_processed(event.event_id):
            prospect.record(ProspectEvent(
                ProspectEventType.DUPLICATE_IGNORED,
                payload={"duplicate_event_id": event.event_id},
                causation_id=event.event_id,
            ))
            return AcquisitionResult(prospect, prospect.current_state)

        prospect.record(event)
        event_type = ProspectEventType(event.event_type)
        if prospect.current_state is ProspectState.HANDED_OFF:
            prospect.mark_processed(event.event_id)
            return AcquisitionResult(prospect, prospect.current_state)
        if prospect.current_state is ProspectState.SUPPRESSED and event_type is not ProspectEventType.OPT_IN_RECORDED:
            prospect.mark_processed(event.event_id)
            return AcquisitionResult(prospect, prospect.current_state)
        self._apply_side_effects(prospect, event, event_type)

        try:
            target = self._target_state(campaign.marketing_dna, prospect, event_type)
        except InvalidDemandTransition as exc:
            prospect.record(ProspectEvent(
                ProspectEventType.TRANSITION_REJECTED,
                payload={"reason": str(exc)},
                causation_id=event.event_id,
            ))
            prospect.mark_processed(event.event_id)
            raise

        if target is prospect.current_state:
            prospect.mark_processed(event.event_id)
            return AcquisitionResult(prospect, prospect.current_state)

        self.state_machine.validate(prospect.current_state, target)
        previous = prospect.current_state
        prospect.record(ProspectEvent(
            ProspectEventType.DECISION_RECORDED,
            payload={"decision_type": "RULE", "target_state": target.value, "score": prospect.score},
            causation_id=event.event_id,
        ))
        prospect._apply_transition(target)
        prospect.record(ProspectEvent(
            ProspectEventType.STATE_CHANGED,
            payload={"from": previous.value, "to": target.value},
            causation_id=event.event_id,
        ))

        handoff = None
        if prospect.current_state is ProspectState.INQUIRED:
            handoff = self._handoff(campaign, prospect, event)
            self.state_machine.validate(prospect.current_state, ProspectState.HANDED_OFF)
            handed_from = prospect.current_state
            prospect._apply_transition(ProspectState.HANDED_OFF)
            prospect.mark_handed_off(handoff.handoff_id)
            prospect.record(ProspectEvent(
                ProspectEventType.HANDOFF_CREATED,
                payload={
                    "handoff_id": handoff.handoff_id,
                    "external_message_id": handoff.external_message_id,
                    "entry_state": handoff.entry_state,
                },
                causation_id=event.event_id,
            ))
            prospect.record(ProspectEvent(
                ProspectEventType.STATE_CHANGED,
                payload={"from": handed_from.value, "to": ProspectState.HANDED_OFF.value},
                causation_id=event.event_id,
            ))

        prospect.mark_processed(event.event_id)
        return AcquisitionResult(prospect, prospect.current_state, handoff=handoff)

    def send_due_step(
        self,
        campaign: Campaign,
        prospect: Prospect,
        *,
        now: datetime | None = None,
    ) -> AcquisitionResult:
        require_live(campaign)
        now = now or utc_now()
        if prospect.current_state in {ProspectState.HANDED_OFF, ProspectState.INQUIRED, ProspectState.SUPPRESSED}:
            return AcquisitionResult(prospect, prospect.current_state)
        steps = compile_welcome_sequence(campaign.marketing_dna)
        if not steps:
            return AcquisitionResult(prospect, prospect.current_state, blocked_reason="no loyalty sequence")
        if not prospect.has_active_consent(ConsentChannel.EMAIL) and not prospect.has_active_consent(ConsentChannel.SMS):
            raise ConsentRequiredError("loyalty sequence requires an active opt-in")
        if prospect.next_sequence_index > len(steps):
            exhausted = ProspectEvent(ProspectEventType.NURTURE_EXHAUSTED.value)
            return self.receive(campaign, prospect, exhausted)

        step = steps[prospect.next_sequence_index - 1]
        if not self._step_is_due(prospect, step, now):
            return AcquisitionResult(prospect, prospect.current_state)

        body = render_step(step, campaign.marketing_dna, first_name=prospect.name)
        message = OutboundMessage(
            channel=step.channel,
            subject=step.purpose.replace("_", " ").title(),
            body=body,
            cta=step.cta,
            claim_ids=step.allowed_claim_ids,
            sequence_index=step.index,
        )
        try:
            assert_claims_allowed(step.allowed_claim_ids, campaign.marketing_dna)
            assert_publishable(message.body, campaign.marketing_dna)
            assert_can_send(prospect, message, campaign.marketing_dna)
        except (ConsentRequiredError, ValueError) as exc:
            prospect.record(ProspectEvent(
                ProspectEventType.SEND_BLOCKED,
                payload={"reason": str(exc), "sequence_index": step.index},
            ))
            raise

        sent = ProspectEvent(
            ProspectEventType.SEQUENCE_STEP_SENT.value,
            payload={"sequence_index": step.index, "purpose": step.purpose},
        )
        result = self.receive(campaign, prospect, sent)
        prospect.next_sequence_index += 1
        return AcquisitionResult(prospect, result.state, outbound=message, handoff=result.handoff)

    def _apply_side_effects(
        self,
        prospect: Prospect,
        event: ProspectEvent,
        event_type: ProspectEventType,
    ) -> None:
        prospect.score += _POINTS.get(event_type, 0)
        payload = dict(event.payload)
        if event_type is ProspectEventType.OPT_IN_RECORDED:
            channel = ConsentChannel(str(payload.get("channel") or "email"))
            prospect.add_consent(ConsentRecord(
                channel=channel,
                action=ConsentAction.GRANT,
                source=str(payload.get("source") or "form"),
                evidence_id=payload.get("evidence_id"),
                recorded_at=event.occurred_at,
            ))
            if prospect.subscribed_at is None:
                prospect.subscribed_at = event.occurred_at
            if payload.get("email"):
                prospect.email = str(payload["email"])
            if payload.get("phone"):
                prospect.phone = str(payload["phone"])
            if payload.get("name"):
                prospect.name = str(payload["name"])
        if event_type is ProspectEventType.UNSUBSCRIBED:
            channel = ConsentChannel(str(payload.get("channel") or "email"))
            prospect.add_consent(ConsentRecord(
                channel=channel,
                action=ConsentAction.REVOKE,
                source=str(payload.get("source") or "unsubscribe"),
                recorded_at=event.occurred_at,
            ))
        if event_type is ProspectEventType.INQUIRY_RECEIVED:
            if payload.get("email"):
                prospect.email = str(payload["email"])
            if payload.get("phone"):
                prospect.phone = str(payload["phone"])
            if payload.get("name"):
                prospect.name = str(payload["name"])

    def _target_state(
        self,
        marketing_dna: Mapping[str, Any],
        prospect: Prospect,
        event_type: ProspectEventType,
    ) -> ProspectState:
        current = prospect.current_state
        if event_type is ProspectEventType.UNSUBSCRIBED:
            return ProspectState.SUPPRESSED
        if event_type is ProspectEventType.INQUIRY_RECEIVED:
            return ProspectState.INQUIRED
        if event_type is ProspectEventType.NURTURE_EXHAUSTED:
            return ProspectState.EXPIRED
        if event_type is ProspectEventType.OPT_IN_RECORDED:
            return ProspectState.NURTURING if current is ProspectState.SUBSCRIBED else ProspectState.SUBSCRIBED
        scoring = dict(marketing_dna.get("scoring") or {})
        intended = current
        if event_type is ProspectEventType.CONTENT_VIEWED or prospect.score >= int(scoring.get("aware_min", 5)):
            intended = _later(intended, ProspectState.AWARE)
        if event_type is ProspectEventType.CONTENT_ENGAGED or prospect.score >= int(scoring.get("engaged_min", 20)):
            intended = _later(intended, ProspectState.ENGAGED)
        if event_type is ProspectEventType.SEQUENCE_STEP_SENT:
            intended = _later(intended, ProspectState.NURTURING)
        if event_type is ProspectEventType.CTA_CLICKED or prospect.score >= int(scoring.get("intent_min", 45)):
            intended = _later(intended, ProspectState.INTENT)
        return intended

    def _handoff(self, campaign: Campaign, prospect: Prospect, event: ProspectEvent) -> InquiryHandoff:
        payload = dict(event.payload)
        channel = str(payload.get("channel") or "website")
        inquiry = str(payload.get("message") or "").strip()
        if not inquiry:
            raise InvalidDemandTransition("inquiry event is missing message text")
        return InquiryHandoff(
            business_id=prospect.business_id,
            prospect_id=prospect.prospect_id,
            campaign_id=campaign.campaign_id,
            channel=channel,
            inquiry_text=inquiry,
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            customer_name=prospect.name,
            email=prospect.email,
            phone=prospect.phone,
            sms_consent=prospect.has_active_consent(ConsentChannel.SMS),
            attribution={
                "source": "flywheel_demand",
                "campaign_id": campaign.campaign_id,
                "prospect_id": prospect.prospect_id,
                "brief_id": payload.get("brief_id"),
                "sequence_index": payload.get("sequence_index"),
            },
        )

    def _step_is_due(self, prospect: Prospect, step: SequenceStep, now: datetime) -> bool:
        start = prospect.subscribed_at or prospect.created_at
        return now >= start + timedelta(hours=step.offset_hours)


def _later(current: ProspectState, candidate: ProspectState) -> ProspectState:
    if current not in _STATE_RANK or candidate not in _STATE_RANK:
        return current
    return candidate if _STATE_RANK[candidate] > _STATE_RANK[current] else current
