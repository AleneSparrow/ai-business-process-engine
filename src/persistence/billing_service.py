"""Self-serve Lemon Squeezy subscription billing for a business's own Flywheel
account.

Not to be confused with `src/domain/commercial.py` / `commercial_service.py`,
which handle a *business's own customers* paying *that business* (quotes,
bookings, payment requests) -- this module is the other side of the
marketplace: a business paying Flywheel for the product itself.

Runs on **Lemon Squeezy**, not Stripe: Stripe's supported-country list does
not include Vietnam, where this business (and its Stripe/Lemon Squeezy
account) is based. Lemon Squeezy is a Merchant of Record -- it is the legal
seller on every transaction, handles global sales-tax/VAT compliance itself,
and explicitly supports Vietnam-based sellers for bank payouts. That MoR
structure shapes this integration in a few ways worth knowing before reading
further:

- There's no separate "create a customer, then a subscription" step --
  a hosted Checkout is created per attempt (`create_checkout_session`) and
  Lemon Squeezy creates its own Customer/Subscription records on completion.
- Free trial length is configured on the Product/Variant in the Lemon
  Squeezy dashboard, not passed as a per-checkout parameter (unlike Stripe's
  `subscription_data.trial_period_days`) -- `Settings.billing_trial_days`
  here is copy-only (what the frontend tells the customer), and must be kept
  in sync with what's actually configured on each variant.
- Business identity travels as `custom_data` on the checkout, echoed back in
  `meta.custom_data` on every related webhook -- Lemon Squeezy's equivalent
  of Stripe's arbitrary object metadata.
- Lemon Squeezy's own `cancelled` status already means "the customer
  cancelled, but access is paid through `ends_at`" -- see
  `ACTIVE_SUBSCRIPTION_STATUSES` in `src/domain/tenancy.py`. There's no
  separate cancel_at_period_end flag to track, unlike Stripe.

Lemon Squeezy is the single source of truth for subscription state. This
service only ever *reads* that state from two places: a synchronous API call
at the moment checkout/portal is requested (to get a redirect URL), and the
webhook, which is what actually keeps `Business.subscription_status` current
as trials convert, cards fail, and subscriptions get cancelled -- all on
Lemon Squeezy's schedule, not in response to any request a user makes to
this app.

The API client is injected (`client`) rather than constructed at module
scope, so this module -- and anything that imports it -- doesn't require
real credentials or network access just to run unrelated tests. Production
wiring (see `src/api/dependencies.py::get_billing_service`) passes no
override, which lazily builds a real `LemonSqueezyClient`.
"""

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from src.config import Settings
from src.domain.tenancy import PLAN_IDS, Business

from .errors import (
    BillingAccountNotFoundError,
    BillingNotConfiguredError,
    InvalidPlanError,
    WebhookSignatureError,
)
from .lemonsqueezy_client import LemonSqueezyClient
from .repositories import UnitOfWork

# Events that carry a full subscription snapshot (data.type == "subscriptions")
# in data.attributes -- status, trial_ends_at, renews_at, ends_at are all
# read directly off these. See
# https://docs.lemonsqueezy.com/help/webhooks/event-types
_SUBSCRIPTION_SNAPSHOT_EVENTS = frozenset({
    "subscription_created",
    "subscription_updated",
    "subscription_cancelled",
    "subscription_resumed",
    "subscription_expired",
    "subscription_paused",
    "subscription_unpaused",
})
# Carries a subscription-invoice object instead (different shape -- no
# status/trial_ends_at/renews_at fields, just subscription_id + invoice
# status) -- handled separately, see _apply_payment_failed.
_PAYMENT_FAILED_EVENTS = frozenset({"subscription_payment_failed"})
_HANDLED_EVENT_TYPES = _SUBSCRIPTION_SNAPSHOT_EVENTS | _PAYMENT_FAILED_EVENTS


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    # Lemon Squeezy sends "2023-01-24T12:43:48.000000Z" -- fromisoformat wants
    # "+00:00" instead of a bare "Z".
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class BillingService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        settings: Settings,
        *,
        client: Any | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._settings = settings
        if client is not None:
            self._client = client
        elif settings.billing_configured:
            self._client = LemonSqueezyClient(settings.lemonsqueezy_api_key)
        else:
            self._client = None

    def _require_configured(self) -> None:
        if not self._settings.billing_configured:
            raise BillingNotConfiguredError(
                "Billing is not configured on this deployment (no LEMONSQUEEZY_API_KEY)"
            )

    def _variant_id_for_plan(self, plan: str) -> str:
        if plan not in PLAN_IDS:
            raise InvalidPlanError(f"unknown plan: {plan!r}")
        variant_id = {
            "starter": self._settings.lemonsqueezy_variant_starter,
            "pro": self._settings.lemonsqueezy_variant_pro,
        }[plan]
        if not variant_id:
            raise InvalidPlanError(f"plan {plan!r} has no configured Lemon Squeezy variant")
        return variant_id

    def _plan_for_variant_id(self, variant_id: int | str | None) -> str | None:
        if variant_id is None:
            return None
        variant_id = str(variant_id)
        if variant_id == self._settings.lemonsqueezy_variant_starter:
            return "starter"
        if variant_id == self._settings.lemonsqueezy_variant_pro:
            return "pro"
        return None

    def get_status(self, business_id: str) -> Business:
        with self._unit_of_work_factory() as unit_of_work:
            business = unit_of_work.businesses.get(business_id)
        if business is None:
            raise KeyError(f"unknown business_id: {business_id}")
        return business

    def create_checkout_session(self, business_id: str, plan: str, owner_email: str) -> str:
        """Returns a Lemon Squeezy-hosted Checkout URL for a new or lapsed
        subscription. `business_id` and `plan` travel as `custom_data` so the
        webhook can attribute events back to this business without a lookup."""
        self._require_configured()
        variant_id = self._variant_id_for_plan(plan)
        with self._unit_of_work_factory() as unit_of_work:
            business = unit_of_work.businesses.get(business_id)
        if business is None:
            raise KeyError(f"unknown business_id: {business_id}")

        response = self._client.create_checkout(
            store_id=self._settings.lemonsqueezy_store_id,
            variant_id=variant_id,
            email=owner_email,
            custom_data={"business_id": business_id, "plan": plan},
            redirect_url=f"{self._settings.frontend_base_url}/app/billing?checkout=success",
        )
        return response["data"]["attributes"]["url"]

    def create_portal_session(self, business_id: str) -> str:
        """Returns a fresh Lemon Squeezy Customer Portal URL where the owner
        can update their card, change plan, or cancel -- entirely self-serve.
        Fetched live (not stored) because the portal URL Lemon Squeezy issues
        is a signed link that expires after 24 hours."""
        self._require_configured()
        with self._unit_of_work_factory() as unit_of_work:
            business = unit_of_work.businesses.get(business_id)
        if business is None:
            raise KeyError(f"unknown business_id: {business_id}")
        if not business.payment_subscription_id:
            raise BillingAccountNotFoundError(
                "This business hasn't started a subscription yet -- nothing to manage"
            )
        response = self._client.get_subscription(business.payment_subscription_id)
        return response["data"]["attributes"]["urls"]["customer_portal"]

    def handle_webhook(self, payload: bytes, signature_header: str | None) -> None:
        """Verifies and applies a Lemon Squeezy webhook event. Unrecognized
        event types (order/customer/license events we don't act on) are
        silently accepted -- there's nothing to retry for those."""
        self._require_configured()
        expected = hmac.new(
            self._settings.lemonsqueezy_webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        if not signature_header or not hmac.compare_digest(expected, signature_header):
            raise WebhookSignatureError("Lemon Squeezy webhook signature mismatch")

        try:
            event = json.loads(payload)
        except ValueError as exc:
            raise WebhookSignatureError(f"malformed webhook payload: {exc}") from exc

        event_name = event.get("meta", {}).get("event_name")
        if event_name not in _HANDLED_EVENT_TYPES:
            return

        with self._unit_of_work_factory() as unit_of_work:
            if event_name in _SUBSCRIPTION_SNAPSHOT_EVENTS:
                self._apply_subscription_snapshot(unit_of_work, event)
            elif event_name in _PAYMENT_FAILED_EVENTS:
                self._apply_payment_failed(unit_of_work, event)
            unit_of_work.commit()

    def _resolve_business_id(
        self,
        unit_of_work: UnitOfWork,
        event: Mapping[str, Any],
        *,
        customer_id: int | str | None,
        subscription_id: int | str | None,
    ) -> str | None:
        custom_data = event.get("meta", {}).get("custom_data") or {}
        business_id = custom_data.get("business_id")
        if business_id:
            return business_id
        if customer_id is not None:
            business = unit_of_work.businesses.get_by_payment_customer_id(str(customer_id))
            if business is not None:
                return business.business_id
        if subscription_id is not None:
            business = unit_of_work.businesses.get_by_payment_subscription_id(str(subscription_id))
            if business is not None:
                return business.business_id
        return None

    def _apply_subscription_snapshot(self, unit_of_work: UnitOfWork, event: Mapping[str, Any]) -> None:
        data = event["data"]
        attributes = data["attributes"]
        subscription_id = data["id"]
        customer_id = attributes.get("customer_id")
        business_id = self._resolve_business_id(
            unit_of_work, event, customer_id=customer_id, subscription_id=subscription_id
        )
        if business_id is None:
            # Nothing in this app to attribute the event to (e.g. a test-mode
            # event fired before any real business ever checked out).
            return
        ends_at = attributes.get("ends_at")
        renews_at = attributes.get("renews_at")
        unit_of_work.businesses.update_billing(
            business_id,
            payment_customer_id=str(customer_id) if customer_id is not None else None,
            payment_subscription_id=str(subscription_id),
            plan=self._plan_for_variant_id(attributes.get("variant_id")),
            subscription_status=attributes.get("status", "incomplete"),
            trial_ends_at=_parse_timestamp(attributes.get("trial_ends_at")),
            # ends_at is set once cancelled/expired; renews_at is the "next
            # charge" date while on_trial/active -- either way this is "the
            # date through which access is paid for".
            current_period_end=_parse_timestamp(ends_at) or _parse_timestamp(renews_at),
        )

    def _apply_payment_failed(self, unit_of_work: UnitOfWork, event: Mapping[str, Any]) -> None:
        attributes = event["data"]["attributes"]
        subscription_id = attributes.get("subscription_id")
        business_id = self._resolve_business_id(
            unit_of_work, event, customer_id=attributes.get("customer_id"), subscription_id=subscription_id
        )
        if business_id is None:
            return
        business = unit_of_work.businesses.get(business_id)
        if business is None:
            return
        unit_of_work.businesses.update_billing(
            business_id,
            payment_customer_id=business.payment_customer_id,
            payment_subscription_id=business.payment_subscription_id,
            plan=business.plan,
            subscription_status="past_due",
            trial_ends_at=business.trial_ends_at,
            current_period_end=business.current_period_end,
        )
