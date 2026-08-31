"""Tenant and versioned Business DNA domain records."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .models import _freeze, _require_aware, _require_text

# Mirrors the Lemon Squeezy Subscription `status` values this app branches on
# (see BillingService) plus "incomplete", used locally for a business that has
# never started checkout. "cancelled" is Lemon Squeezy's own status for "the
# customer cancelled, but the subscription remains valid until `ends_at`" --
# distinct from "expired", which is the actual terminal end. See
# https://docs.lemonsqueezy.com/api/subscriptions/the-subscription-object
SUBSCRIPTION_STATUSES = frozenset({
    "incomplete", "on_trial", "active", "paused", "past_due", "unpaid", "cancelled", "expired",
})
# The only statuses that grant staff-dashboard access -- see
# `require_active_subscription` in src/api/dependencies.py. "cancelled" is
# included deliberately: the customer already paid for the current period,
# access should last until Lemon Squeezy actually fires `subscription_expired`.
ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"on_trial", "active", "cancelled"})
PLAN_IDS = frozenset({"starter", "pro"})


@dataclass(frozen=True, slots=True)
class Business:
    business_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    payment_customer_id: str | None = None
    payment_subscription_id: str | None = None
    plan: str | None = None
    subscription_status: str = "incomplete"
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    billing_event_at: datetime | None = None
    # New tenants start in test mode, but this default stays False so a
    # migration never retrospectively reclassifies an existing tenant's
    # historical cases. BusinessProvisioningService opts new tenants in.
    test_mode_enabled: bool = False
    # A reporting baseline hides earlier cases from aggregate metrics without
    # deleting cases, conversations, or their immutable event history.
    stats_since: datetime | None = None
    """The Lemon Squeezy snapshot timestamp (subscription/invoice
    `updated_at`, falling back to `created_at`) of the most recent webhook
    event actually applied to the billing fields above. Used to reject an
    out-of-order delivery -- e.g. a delayed `subscription_created` retry
    arriving after a `subscription_cancelled` -- rather than letting it
    resurrect access. None means no event carrying a usable timestamp has
    been applied yet, so there is nothing to protect against overwriting.
    See BillingService.handle_webhook / BusinessRepository.update_billing."""

    def __post_init__(self) -> None:
        _require_text(self.business_id, "business_id")
        _require_text(self.name, "name")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.updated_at, "updated_at")
        if self.subscription_status not in SUBSCRIPTION_STATUSES:
            raise ValueError(f"unknown subscription_status: {self.subscription_status!r}")
        if self.plan is not None and self.plan not in PLAN_IDS:
            raise ValueError(f"unknown plan: {self.plan!r}")
        if self.trial_ends_at is not None:
            _require_aware(self.trial_ends_at, "trial_ends_at")
        if self.current_period_end is not None:
            _require_aware(self.current_period_end, "current_period_end")
        if self.billing_event_at is not None:
            _require_aware(self.billing_event_at, "billing_event_at")
        if self.stats_since is not None:
            _require_aware(self.stats_since, "stats_since")

    @property
    def has_billing_access(self) -> bool:
        """Whether this business's subscription currently grants staff-dashboard
        access -- see `require_active_subscription`. Public lead intake and the
        embeddable widget are deliberately NOT gated on this: a lapsed payment
        blocks the owner's own dashboard, not the automation their customers
        are already relying on."""
        return self.subscription_status in ACTIVE_SUBSCRIPTION_STATUSES


@dataclass(frozen=True, slots=True)
class BusinessDNAVersion:
    business_id: str
    version: int
    configuration: Mapping[str, Any]
    created_at: datetime
    active: bool

    def __post_init__(self) -> None:
        _require_text(self.business_id, "business_id")
        if self.version < 1:
            raise ValueError("Business DNA version must be positive")
        _require_aware(self.created_at, "created_at")
        object.__setattr__(self, "configuration", _freeze(self.configuration))
