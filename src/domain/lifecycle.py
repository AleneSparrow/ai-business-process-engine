"""Staff overrides when a step finished *outside* the conversation.

The happy path does not go through these buttons. The assistant closes
WON → PAID → COMPLETED → REVIEW_REQUESTED in chat (customer wording) and
via the post-visit sweep. Staff actions exist so an owner can record an
offline payment or a job that finished without a customer message.
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
    """Offline overrides only — the assistant already runs these steps in chat."""
    if state is ProcessState.WON:
        return (LifecycleAction.RECORD_PAYMENT, LifecycleAction.MARK_COMPLETED)
    if state is ProcessState.PAID:
        return (LifecycleAction.MARK_COMPLETED,)
    if state is ProcessState.COMPLETED:
        return (LifecycleAction.REQUEST_REVIEW,)
    if state is ProcessState.QUALIFIED:
        return (LifecycleAction.CONFIRM_NEXT_STEP,)
    return ()
