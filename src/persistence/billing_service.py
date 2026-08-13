"""Self-serve Stripe subscription billing for a business's own Atelier account.

Not to be confused with `src/domain/commercial.py` / `commercial_service.py`,
which handle a *business's own customers* paying *that business* (quotes,
bookings, payment requests) -- this module is the other side of the
marketplace: a business paying Atelier for the product itself.

Stripe is the single source of truth for subscription state. This service
only ever *reads* that state from two places: a synchronous API call at the
moment checkout/portal is requested (to get a redirect URL), and the Stripe
webhook, which is what actually keeps `Business.subscription_status` current
as trials convert, cards fail, and subscriptions get cancelled -- all of
which happen on Stripe's schedule, not in response to any request a user
makes to this app. See `ACTIVE_SUBSCRIPTION_STATUSES` in
`src/domain/tenancy.py` for which statuses grant dashboard access, enforced
by `require_active_subscription` in `src/api/dependencies.py`.

The Stripe SDK itself is injected (`stripe_client`) rather than imported at
module scope, so this module -- and anything that imports it -- doesn't
require the `stripe` package to be installed just to run unrelated tests.
Production wiring (see `src/api/dependencies.py::get_billing_service`) passes
no override, which lazily imports the real package.
"""

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
from .repositories import UnitOfWork

_HANDLED_EVENT_TYPES = frozenset({
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
})


def _from_unix(value: float | int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


class BillingService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        settings: Settings,
        *,
        stripe_client: Any | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._settings = settings
        if stripe_client is not None:
            self._stripe = stripe_client
        elif settings.billing_configured:
            import stripe  # local import: only required when billing is actually configured

            stripe.api_key = settings.stripe_secret_key
            self._stripe = stripe
        else:
            self._stripe = None

    def _require_configured(self) -> None:
        if not self._settings.billing_configured:
            raise BillingNotConfiguredError(
                "Billing is not configured on this deployment (no STRIPE_SECRET_KEY)"
            )

    def _price_id_for_plan(self, plan: str) -> str:
        if plan not in PLAN_IDS:
            raise InvalidPlanError(f"unknown plan: {plan!r}")
        price_id = {
            "starter": self._settings.stripe_price_starter,
            "pro": self._settings.stripe_price_pro,
        }[plan]
        if not price_id:
            raise InvalidPlanError(f"plan {plan!r} has no configured Stripe price")
        return price_id

    def get_status(self, business_id: str) -> Business:
        with self._unit_of_work_factory() as unit_of_work:
            business = unit_of_work.businesses.get(business_id)
        if business is None:
            raise KeyError(f"unknown business_id: {business_id}")
        return business

    def create_checkout_session(self, business_id: str, plan: str, owner_email: str) -> str:
        """Returns a Stripe-hosted Checkout URL for a new or lapsed subscription.
        Reuses the business's existing Stripe customer if one already exists
        (e.g. retrying after a cancelled checkout) instead of creating a duplicate."""
        self._require_configured()
        price_id = self._price_id_for_plan(plan)
        with self._unit_of_work_factory() as unit_of_work:
            business = unit_of_work.businesses.get(business_id)
        if business is None:
            raise KeyError(f"unknown business_id: {business_id}")

        base = self._settings.frontend_base_url
        params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "client_reference_id": business_id,
            "metadata": {"business_id": business_id, "plan": plan},
            "subscription_data": {
                "trial_period_days": self._settings.billing_trial_days,
                "metadata": {"business_id": business_id, "plan": plan},
            },
            "success_url": f"{base}/app/billing?checkout=success",
            "cancel_url": f"{base}/app/billing?checkout=cancelled",
        }
        if business.stripe_customer_id:
            params["customer"] = business.stripe_customer_id
        else:
            params["customer_email"] = owner_email

        session = self._stripe.checkout.Session.create(**params)
        return session["url"]

    def create_portal_session(self, business_id: str) -> str:
        """Returns a Stripe-hosted Billing Portal URL where the owner can update
        their card, change plan, or cancel -- entirely self-serve, no support
        ticket or manual action on our side."""
        self._require_configured()
        with self._unit_of_work_factory() as unit_of_work:
            business = unit_of_work.businesses.get(business_id)
        if business is None:
            raise KeyError(f"unknown business_id: {business_id}")
        if not business.stripe_customer_id:
            raise BillingAccountNotFoundError(
                "This business hasn't started a subscription yet -- nothing to manage"
            )
        session = self._stripe.billing_portal.Session.create(
            customer=business.stripe_customer_id,
            return_url=f"{self._settings.frontend_base_url}/app/billing",
        )
        return session["url"]

    def handle_webhook(self, payload: bytes, sig_header: str | None) -> None:
        """Verifies and applies a Stripe webhook event. Unrecognized event types
        (Stripe sends dozens we don't act on) are silently accepted -- returning
        200 for anything we don't specifically handle is the documented, correct
        behavior; the alternative just makes Stripe retry forever for no benefit."""
        self._require_configured()
        try:
            event = self._stripe.Webhook.construct_event(
                payload, sig_header, self._settings.stripe_webhook_secret
            )
        except self._stripe.error.SignatureVerificationError as exc:
            raise WebhookSignatureError(str(exc)) from exc
        except ValueError as exc:  # malformed JSON payload
            raise WebhookSignatureError(str(exc)) from exc

        event_type = event["type"]
        if event_type not in _HANDLED_EVENT_TYPES:
            return

        stripe_object = event["data"]["object"]
        with self._unit_of_work_factory() as unit_of_work:
            business_id = self._resolve_business_id(unit_of_work, stripe_object)
            if business_id is None:
                # Nothing in this app to attribute the event to (e.g. a Stripe
                # test-mode event fired before any real business ever checked
                # out). Not an error -- just nothing to do.
                return
            if event_type == "checkout.session.completed":
                self._apply_checkout_completed(unit_of_work, business_id, stripe_object)
            elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
                self._apply_subscription(unit_of_work, business_id, stripe_object)
            elif event_type == "customer.subscription.deleted":
                self._apply_subscription(unit_of_work, business_id, stripe_object, force_status="canceled")
            elif event_type == "invoice.payment_failed":
                self._apply_payment_failed(unit_of_work, business_id, stripe_object)
            unit_of_work.commit()

    @staticmethod
    def _resolve_business_id(unit_of_work: UnitOfWork, stripe_object: Mapping[str, Any]) -> str | None:
        metadata = stripe_object.get("metadata") or {}
        business_id = metadata.get("business_id") or stripe_object.get("client_reference_id")
        if business_id:
            return business_id
        customer_id = stripe_object.get("customer")
        if not customer_id:
            return None
        business = unit_of_work.businesses.get_by_stripe_customer_id(customer_id)
        return business.business_id if business else None

    @staticmethod
    def _apply_checkout_completed(
        unit_of_work: UnitOfWork, business_id: str, session_obj: Mapping[str, Any]
    ) -> None:
        metadata = session_obj.get("metadata") or {}
        unit_of_work.businesses.update_billing(
            business_id,
            stripe_customer_id=session_obj.get("customer"),
            stripe_subscription_id=session_obj.get("subscription"),
            plan=metadata.get("plan"),
            # The full subscription (trial_end, current_period_end, ...) arrives
            # moments later via customer.subscription.created/updated -- this
            # just establishes the link and an optimistic "trialing" status so
            # the dashboard unblocks immediately rather than waiting on a second
            # webhook round-trip.
            subscription_status="trialing",
            trial_ends_at=None,
            current_period_end=None,
            cancel_at_period_end=False,
        )

    @staticmethod
    def _apply_subscription(
        unit_of_work: UnitOfWork,
        business_id: str,
        subscription_obj: Mapping[str, Any],
        *,
        force_status: str | None = None,
    ) -> None:
        metadata = subscription_obj.get("metadata") or {}
        unit_of_work.businesses.update_billing(
            business_id,
            stripe_customer_id=subscription_obj.get("customer"),
            stripe_subscription_id=subscription_obj.get("id"),
            plan=metadata.get("plan"),
            subscription_status=force_status or subscription_obj.get("status", "incomplete"),
            trial_ends_at=_from_unix(subscription_obj.get("trial_end")),
            current_period_end=_from_unix(subscription_obj.get("current_period_end")),
            cancel_at_period_end=bool(subscription_obj.get("cancel_at_period_end", False)),
        )

    @staticmethod
    def _apply_payment_failed(
        unit_of_work: UnitOfWork, business_id: str, invoice_obj: Mapping[str, Any]
    ) -> None:
        business = unit_of_work.businesses.get(business_id)
        if business is None:
            return
        unit_of_work.businesses.update_billing(
            business_id,
            stripe_customer_id=invoice_obj.get("customer"),
            stripe_subscription_id=business.stripe_subscription_id,
            plan=business.plan,
            subscription_status="past_due",
            trial_ends_at=business.trial_ends_at,
            current_period_end=business.current_period_end,
            cancel_at_period_end=business.cancel_at_period_end,
        )
