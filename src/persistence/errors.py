"""Persistence errors with domain-level meaning."""


class PersistenceError(RuntimeError):
    pass


class IdempotencyCollisionError(PersistenceError):
    """The same message identity was reused for different content."""


class IdempotencyInProgressError(PersistenceError):
    """A message claim exists but its result is not complete."""


class StaleCaseError(PersistenceError):
    """A case changed after it was loaded and cannot be overwritten safely."""
