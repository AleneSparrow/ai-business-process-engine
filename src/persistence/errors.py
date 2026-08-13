"""Persistence errors with domain-level meaning."""


class PersistenceError(RuntimeError):
    pass


class IdempotencyCollisionError(PersistenceError):
    """The same message identity was reused for different content."""


class IdempotencyInProgressError(PersistenceError):
    """A message claim exists but its result is not complete."""


class MessageScopeError(PersistenceError):
    """An incoming message violates tenant-scoped intake policy."""


class StaleCaseError(PersistenceError):
    """A case changed after it was loaded and cannot be overwritten safely."""


class StaleBookingError(PersistenceError):
    """A booking changed after it was loaded and cannot be overwritten safely."""


class StaleQuoteError(PersistenceError):
    """A quote changed after it was loaded and cannot be overwritten safely."""


class StalePaymentRequestError(PersistenceError):
    """A payment request changed after it was loaded and cannot be overwritten safely."""


class ConversationTokenError(PersistenceError):
    """An anonymous conversation token is invalid for the requested tenant."""


class ConversationTokenExpiredError(ConversationTokenError):
    """An anonymous conversation token has expired or been revoked."""


class StaffConversationNotFoundError(PersistenceError):
    """A staff action referenced a conversation_id that doesn't exist for this business."""


class ConversationNotLinkedError(PersistenceError):
    """A staff action needs a case, but the conversation has none linked yet."""


class CaseNotAwaitingApprovalError(PersistenceError):
    """A staff resolve action was requested but the case has no pending human
    approval to give -- it is not in NEEDS_HUMAN, or has no pending_transition
    (see ProcessEngine.receive / DecisionRouter._escalation)."""


class ConversationClosedError(PersistenceError):
    """A staff action was requested on a conversation that is already closed."""
