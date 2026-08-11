"""Policy boundary between rules, AI judgment, and human approval."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from src.domain.models import Action, Decision, DecisionType, ProcessCase, ProcessEvent
from src.domain.states import ProcessState


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    decision_type: DecisionType
    target_state: ProcessState
    confidence: float | None = None
    high_risk: bool = False
    action: Action | None = None
    approved_by: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.approved_by is not None and not self.approved_by.strip():
            raise ValueError("approved_by must not be empty")
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


class AIDecisionProvider(Protocol):
    def decide(self, case: ProcessCase, event: ProcessEvent, request: DecisionRequest) -> Decision: ...


class PlaceholderAIProvider:
    """Deterministic stand-in; replace through dependency injection later."""

    def decide(self, case: ProcessCase, event: ProcessEvent, request: DecisionRequest) -> Decision:
        confidence = request.confidence if request.confidence is not None else 0.0
        return Decision(
            decision_type=DecisionType.AI,
            approved=True,
            target_state=request.target_state,
            confidence=confidence,
            reason="Placeholder AI recommendation; no external model was called",
        )


class DecisionRouter:
    ALWAYS_HIGH_RISK_ACTIONS = frozenset({
        "capture_payment", "issue_refund", "change_price", "make_legal_commitment"
    })

    def __init__(self, ai_provider: AIDecisionProvider | None = None, confidence_threshold: float = 0.8) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        self.ai_provider = ai_provider or PlaceholderAIProvider()
        self.confidence_threshold = confidence_threshold

    def route(self, case: ProcessCase, event: ProcessEvent, request: DecisionRequest) -> Decision:
        if request.decision_type is DecisionType.HUMAN:
            if request.approved_by:
                return Decision(
                    DecisionType.HUMAN, True, "Approved by an identified human",
                    request.target_state, 1.0, metadata={"approved_by": request.approved_by},
                )
            return self._escalation("Human approval explicitly requested", request.target_state)

        action_is_high_risk = bool(
            request.high_risk
            or (request.action and (
                request.action.high_risk
                or request.action.action_type in self.ALWAYS_HIGH_RISK_ACTIONS
            ))
        )
        if action_is_high_risk:
            return self._escalation("High-risk work requires identified human approval", request.target_state)

        if request.decision_type is DecisionType.RULE:
            return Decision(DecisionType.RULE, True, "Deterministic rule approved", request.target_state, 1.0)

        decision = self.ai_provider.decide(case, event, request)
        if decision.decision_type is not DecisionType.AI:
            return self._escalation("AI provider returned an invalid decision type", request.target_state)
        if decision.target_state is not request.target_state:
            return self._escalation("AI provider changed the requested target state", request.target_state)
        if not decision.approved:
            return self._escalation("AI provider did not approve the recommendation", request.target_state)
        confidence = decision.confidence if decision.confidence is not None else 0.0
        if confidence < self.confidence_threshold:
            return self._escalation("AI confidence is below the configured threshold", request.target_state, confidence)
        return decision

    @staticmethod
    def _escalation(
        reason: str,
        pending_target: ProcessState,
        confidence: float | None = None,
    ) -> Decision:
        return Decision(
            DecisionType.HUMAN,
            approved=True,
            reason=reason,
            target_state=ProcessState.NEEDS_HUMAN,
            confidence=confidence,
            requires_human=True,
            metadata={"pending_target": pending_target.value},
        )
