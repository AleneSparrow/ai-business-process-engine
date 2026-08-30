"""Event-driven orchestration for one in-memory process case."""

from src.domain.events import EventType
from src.domain.models import Decision, DecisionType, ProcessCase, ProcessEvent
from src.domain.state_machine import InvalidTransition, StateMachine
from src.domain.states import ProcessState

from .decision_router import DecisionRequest, DecisionRouter


class ProcessEngine:
    def __init__(self, state_machine: StateMachine | None = None, decision_router: DecisionRouter | None = None) -> None:
        self.state_machine = state_machine or StateMachine()
        self.decision_router = decision_router or DecisionRouter()

    def receive(self, case: ProcessCase, event: ProcessEvent, request: DecisionRequest) -> Decision:
        """Process a trigger once and apply its approved or escalated transition."""
        if case.has_processed(event.event_id):
            case.record(ProcessEvent(
                EventType.DUPLICATE_IGNORED,
                payload={"duplicate_event_id": event.event_id},
                causation_id=event.event_id,
            ))
            return Decision(request.decision_type, False, "Duplicate event ignored")

        case.record(event)
        decision = self.decision_router.route(case, event, request)
        target = decision.target_state

        case.record(ProcessEvent(
            EventType.DECISION_RECORDED,
            payload={
                "decision_type": decision.decision_type.value,
                "approved": decision.approved,
                "reason": decision.reason,
                "target_state": target.value if target else None,
                "confidence": decision.confidence,
                "requires_human": decision.requires_human,
                "metadata": decision.metadata,
            },
            causation_id=event.event_id,
        ))

        try:
            if target is None:
                raise InvalidTransition("Decision did not provide a target state")
            if not decision.approved:
                raise InvalidTransition("Decision was not approved")
            if case.current_state is ProcessState.NEEDS_HUMAN:
                # "Identified human approved this exact decision" is this
                # engine's call, not the state machine's -- StateMachine
                # only knows about states, not who is allowed to move them.
                if decision.decision_type is not DecisionType.HUMAN or not request.approved_by:
                    raise InvalidTransition("NEEDS_HUMAN requires approval by an identified human")
                # Whether the resulting state change is even a legal exit
                # from NEEDS_HUMAN (case really is NEEDS_HUMAN, a pending
                # transition really was recorded, target matches it exactly)
                # is the state machine's call -- see validate_human_resume.
                self.state_machine.validate_human_resume(case.current_state, case.pending_transition, target)
            else:
                self.state_machine.validate(case.current_state, target)
        except InvalidTransition as exc:
            case.record(ProcessEvent(
                EventType.TRANSITION_REJECTED,
                payload={"reason": str(exc), "target_state": getattr(target, "value", None)},
                causation_id=event.event_id,
            ))
            case.mark_processed(event.event_id)
            raise

        previous = case.current_state
        case._apply_transition(target)
        if target is ProcessState.NEEDS_HUMAN:
            pending = decision.metadata.get("pending_target")
            if not isinstance(pending, str):
                raise RuntimeError("Escalation decision omitted its pending target")
            case.set_pending_transition(ProcessState(pending))
        elif previous is ProcessState.NEEDS_HUMAN:
            case.clear_pending_transition()
        case.record(ProcessEvent(
            EventType.STATE_CHANGED,
            payload={"from": previous.value, "to": target.value},
            causation_id=event.event_id,
        ))
        case.mark_processed(event.event_id)
        return decision
