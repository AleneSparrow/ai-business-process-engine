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


class BillingNotConfiguredError(PersistenceError):
    """Lemon Squeezy isn't configured (no LEMONSQUEEZY_API_KEY) -- billing
    endpoints are reachable but can't do anything yet. Distinct from a 500:
    this is an expected, named deployment state (e.g. local dev, or before
    the Lemon Squeezy store is set up)."""


class InvalidPlanError(PersistenceError):
    """A checkout was requested for a plan id that isn't `starter` or `pro`, or
    whose corresponding LEMONSQUEEZY_VARIANT_* env var isn't set."""


class BillingAccountNotFoundError(PersistenceError):
    """A portal session was requested for a business that never started
    checkout, so it has no Lemon Squeezy subscription to manage yet."""


class BillingAlreadyActiveError(PersistenceError):
    """A business with current billing access must use the provider portal."""


class DemandProductNotConfiguredError(PersistenceError):
    """Demand checkout was requested but LEMONSQUEEZY_VARIANT_DEMAND is unset.

    Optional on purpose: existing Flywheel deploys must still boot. The
    Billing page returns 422 until Alena creates the Lemon Squeezy product
    and sets the variant id.
    """


class DemandRequiresFlywheelSubscriptionError(PersistenceError):
    """Demand is an add-on: the business must already have Flywheel access."""


class DemandAlreadyActiveError(PersistenceError):
    """Demand is already paid through; manage it in the customer portal."""


class DemandSubscriptionRequiredError(PersistenceError):
    """Demand handed off an inquiry, but this business has no Demand add-on."""


class WebhookSignatureError(PersistenceError):
    """A request to the Lemon Squeezy webhook endpoint failed signature
    verification -- either not actually from Lemon Squeezy, or signed with a
    different webhook secret (or a malformed payload)."""
