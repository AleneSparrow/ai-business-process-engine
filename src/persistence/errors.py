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
