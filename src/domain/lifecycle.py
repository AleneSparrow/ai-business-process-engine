"""Staff-driven post-sale actions that close the lead-to-cash loop.

AI never records payment, marks work complete, or invents a review request.
These transitions are explicit, auditable RULE/HUMAN actions on states the
graph already allows: WON → PAID → COMPLETED → REVIEW_REQUESTED → REACTIVATION.
"""

from src.domain.states import ProcessState


class LifecycleAction:
    RECORD_PAYMENT = "record_payment"
    MARK_COMPLETED = "mark_completed"
    REQUEST_REVIEW = "request_review"
    CONFIRM_NEXT_STEP = "confirm_next_step"


ALLOWED_LIFECYCLE_ACTIONS = frozenset({
    LifecycleAction.RECORD_PAYMENT,
    LifecycleAction.MARK_COMPLETED,
    LifecycleAction.REQUEST_REVIEW,
    LifecycleAction.CONFIRM_NEXT_STEP,
})


def actions_for_state(state: ProcessState) -> tuple[str, ...]:
    """Which staff buttons are *plausible* for this case state.

    The service still validates path-specific preconditions (a QUALIFIED case
    is only confirmable on the direct-next-step path; mark-completed from WON
    requires payment to be settled or absent).
    """
    if state is ProcessState.WON:
        return (LifecycleAction.RECORD_PAYMENT, LifecycleAction.MARK_COMPLETED)
    if state is ProcessState.PAID:
        return (LifecycleAction.MARK_COMPLETED,)
    if state is ProcessState.COMPLETED:
        return (LifecycleAction.REQUEST_REVIEW,)
    if state is ProcessState.QUALIFIED:
        return (LifecycleAction.CONFIRM_NEXT_STEP,)
    return ()
