"""Tenant and versioned Business DNA domain records."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .models import _freeze, _require_aware, _require_text

# Mirrors the Stripe Subscription `status` values this app actually branches on
# (see BillingService) plus "incomplete", used locally for a business that has
# never started checkout. Stripe also has "unpaid" and "paused" -- treated the
# same as "past_due" (blocks dashboard access, doesn't nuke the record).
SUBSCRIPTION_STATUSES = frozenset({
    "incomplete", "trialing", "active", "past_due", "unpaid", "canceled",
})
# The only statuses that grant staff-dashboard access -- see
# `require_active_subscription` in src/api/dependencies.py.
ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"trialing", "active"})
PLAN_IDS = frozenset({"starter", "pro"})


@dataclass(frozen=True, slots=True)
class Business:
    business_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    plan: str | None = None
    subscription_status: str = "incomplete"
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False

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
