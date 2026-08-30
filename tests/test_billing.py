"""Self-serve Lemon Squeezy billing: BillingService directly (fake Lemon
Squeezy client -- see FakeLemonSqueezyClient below) plus the HTTP layer
(billing routes, the require_active_subscription gate on the dashboard, and
that Settings/Business DNA stay reachable regardless of subscription status).

The real network is never touched here -- BillingService takes an injectable
`client`, so these tests exercise all of this module's own logic (checkout/
portal params, webhook event routing + signature verification, business_id
resolution, status/date mapping) without needing a real Lemon Squeezy API key
or any network access. See BillingService's module docstring for why Lemon
Squeezy (not Stripe) and what that changes about the shape of this code:
Vietnam, where this business is based, isn't in Stripe's supported-country
list.
"""

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_billing_service
from src.config import Settings
from src.domain.auth import StaffUser
from src.domain.business_dna_builder import OnboardingInput, OnboardingService, build_business_dna
from src.persistence.billing_service import BillingService
from src.persistence.errors import (
    BillingAlreadyActiveError,
    BillingAccountNotFoundError,
    BillingNotConfiguredError,
    InvalidPlanError,
    WebhookSignatureError,
)
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine

_STORE_ID = "store_fake_1"
_VARIANT_STARTER = "variant_starter_fake"
_VARIANT_PRO = "variant_pro_fake"
_WEBHOOK_SECRET = "whsec_test"


# --- Fake Lemon Squeezy client -------------------------------------------------------


class FakeLemonSqueezyClient:
    """Stands in for LemonSqueezyClient -- records every call so tests can
    assert on the exact params sent, and returns JSON:API-shaped responses
    matching what the real client hands back to BillingService."""

    def __init__(
        self,
        *,
        checkout_url: str = "https://checkout.lemonsqueezy.test/session",
        portal_url: str = "https://portal.lemonsqueezy.test/manage",
    ) -> None:
        self.checkout_calls: list[dict] = []
        self.portal_calls: list[str] = []
        self._checkout_url = checkout_url
        self._portal_url = portal_url

    def create_checkout(self, **kwargs) -> dict:
        self.checkout_calls.append(kwargs)
        return {"data": {"attributes": {"url": self._checkout_url}}}

    def get_subscription(self, subscription_id: str) -> dict:
        self.portal_calls.append(subscription_id)
        return {"data": {"attributes": {"urls": {"customer_portal": self._portal_url}}}}


def _billing_settings(**overrides) -> Settings:
    defaults = dict(
        database_url="sqlite+pysqlite:///:memory:",
        app_env="test",
        lemonsqueezy_api_key="ls_test_fake",
        lemonsqueezy_webhook_secret=_WEBHOOK_SECRET,
        lemonsqueezy_store_id=_STORE_ID,
        lemonsqueezy_variant_starter=_VARIANT_STARTER,
        lemonsqueezy_variant_pro=_VARIANT_PRO,
        frontend_base_url="http://localhost:5173",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _sign(payload: bytes, secret: str = _WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _subscription_event(
    event_name: str,
    *,
    subscription_id: str,
    customer_id: str | None = None,
    variant_id: str | None = None,
    status: str = "active",
    trial_ends_at: str | None = None,
    renews_at: str | None = None,
    ends_at: str | None = None,
    custom_data: dict | None = None,
    updated_at: str | None = None,
    created_at: str | None = None,
    nonce: str | None = None,
) -> bytes:
    """Builds a `subscription_*` webhook payload -- these carry a full
    subscription snapshot in data.attributes (data.type == "subscriptions").

    `updated_at`/`created_at` mirror the real Lemon Squeezy subscription
    object's own timestamps (https://docs.lemonsqueezy.com/api/subscriptions/
    the-subscription-object) -- BillingService reads these to reject an
    out-of-order delivery; omit them (as most tests here do, since ordering
    is untested by default) to exercise the "no comparable timestamp"
    fallback. `nonce` exists purely so two calls that are otherwise
    byte-for-byte identical (e.g. simulating a genuinely distinct delivery
    of the "same" logical event, as opposed to a Lemon Squeezy retry of one
    delivery) don't collide on the dedup fingerprint, which hashes raw
    payload bytes."""
    attributes = {
        "customer_id": customer_id,
        "variant_id": variant_id,
        "status": status,
        "trial_ends_at": trial_ends_at,
        "renews_at": renews_at,
        "ends_at": ends_at,
    }
    if updated_at is not None:
        attributes["updated_at"] = updated_at
    if created_at is not None:
        attributes["created_at"] = created_at
    if nonce is not None:
        attributes["_nonce"] = nonce
    return json.dumps(
        {
            "meta": {"event_name": event_name, "custom_data": custom_data or {}},
            "data": {"type": "subscriptions", "id": subscription_id, "attributes": attributes},
        }
    ).encode("utf-8")


def _payment_failed_event(
    *,
    subscription_id: str,
    customer_id: str | None = None,
    custom_data: dict | None = None,
    updated_at: str | None = None,
) -> bytes:
    """Builds a `subscription_payment_failed` payload -- a different shape
    (a subscription-invoice object), see BillingService._apply_payment_failed."""
    attributes = {
        "subscription_id": subscription_id,
        "customer_id": customer_id,
        "status": "pending",
    }
    if updated_at is not None:
        attributes["updated_at"] = updated_at
    return json.dumps(
        {
            "meta": {"event_name": "subscription_payment_failed", "custom_data": custom_data or {}},
            "data": {"type": "subscription-invoices", "id": "inv_1", "attributes": attributes},
        }
    ).encode("utf-8")


# --- Service-level fixtures ---------------------------------------------------------


@pytest.fixture
def uow_factory(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'billing.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    yield SQLAlchemyUnitOfWork.factory_for_engine(engine)
    engine.dispose()


def _make_business(uow_factory, business_id: str = "acme-co") -> None:
    onboarding = OnboardingInput(
        business_id=business_id,
        business_name="Acme Co",
        industry="Consulting",
        tone="Friendly & direct",
        services=(OnboardingService("Consulting call", ("What do you need help with?",)),),
        service_zip_codes=(),
        enforce_service_area=False,
    )
    configuration = build_business_dna(onboarding)
    with uow_factory() as unit_of_work:
        from src.domain.models import utc_now
        from src.domain.tenancy import Business

        unit_of_work.businesses.add(Business(business_id, "Acme Co", utc_now(), utc_now()))
        unit_of_work.business_dna.add_version(business_id, configuration)
        unit_of_work.commit()


# --- BillingService: checkout / portal ----------------------------------------------


def test_checkout_session_uses_owner_email_and_carries_custom_data(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeLemonSqueezyClient()
    service = BillingService(uow_factory, _billing_settings(), client=fake)

    url = service.create_checkout_session("acme-co", "starter", "owner@example.com")

    assert url == "https://checkout.lemonsqueezy.test/session"
    call = fake.checkout_calls[0]
    assert call["email"] == "owner@example.com"
    assert call["store_id"] == _STORE_ID
    assert call["variant_id"] == _VARIANT_STARTER
    assert call["custom_data"] == {"business_id": "acme-co", "plan": "starter"}
    assert call["redirect_url"] == "http://localhost:5173/app/billing?checkout=success"


def test_checkout_session_picks_variant_by_plan(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeLemonSqueezyClient()
    service = BillingService(uow_factory, _billing_settings(), client=fake)

    service.create_checkout_session("acme-co", "pro", "owner@example.com")

    assert fake.checkout_calls[0]["variant_id"] == _VARIANT_PRO


def test_checkout_session_rejects_unknown_plan(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    with pytest.raises(InvalidPlanError):
        service.create_checkout_session("acme-co", "enterprise", "owner@example.com")


def test_checkout_session_requires_billing_configured(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, Settings(database_url="sqlite+pysqlite:///:memory:", app_env="test"))
    with pytest.raises(BillingNotConfiguredError):
        service.create_checkout_session("acme-co", "starter", "owner@example.com")


def test_checkout_session_rejects_second_active_subscription(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeLemonSqueezyClient()
    service = BillingService(uow_factory, _billing_settings(), client=fake)
    with uow_factory() as unit_of_work:
        unit_of_work.businesses.update_billing(
            "acme-co",
            payment_customer_id="cus_existing",
            payment_subscription_id="sub_existing",
            plan="starter",
            subscription_status="active",
            trial_ends_at=None,
            current_period_end=None,
        )
        unit_of_work.commit()

    with pytest.raises(BillingAlreadyActiveError):
        service.create_checkout_session("acme-co", "pro", "owner@example.com")
    assert fake.checkout_calls == []


@pytest.mark.parametrize("status", ("incomplete", "expired"))
def test_checkout_session_allows_incomplete_or_lapsed_business(uow_factory, status: str) -> None:
    _make_business(uow_factory)
    fake = FakeLemonSqueezyClient()
    service = BillingService(uow_factory, _billing_settings(), client=fake)
    with uow_factory() as unit_of_work:
        unit_of_work.businesses.update_billing(
            "acme-co",
            payment_customer_id="cus_lapsed",
            payment_subscription_id="sub_lapsed",
            plan="starter",
            subscription_status=status,
            trial_ends_at=None,
            current_period_end=None,
        )
        unit_of_work.commit()

    url = service.create_checkout_session("acme-co", "pro", "owner@example.com")

    assert url == "https://checkout.lemonsqueezy.test/session"
    assert len(fake.checkout_calls) == 1


def test_portal_session_requires_existing_subscription(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    with pytest.raises(BillingAccountNotFoundError):
        service.create_portal_session("acme-co")


def test_portal_session_fetches_fresh_url_for_existing_subscription(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeLemonSqueezyClient()
    service = BillingService(uow_factory, _billing_settings(), client=fake)
    with uow_factory() as unit_of_work:
        unit_of_work.businesses.update_billing(
            "acme-co",
            payment_customer_id="cus_existing",
            payment_subscription_id="sub_existing",
            plan="starter",
            subscription_status="active",
            trial_ends_at=None,
            current_period_end=None,
        )
        unit_of_work.commit()

    url = service.create_portal_session("acme-co")

    assert url == "https://portal.lemonsqueezy.test/manage"
    # Fetched live, not stored -- Lemon Squeezy's portal URL is a signed link
    # that expires after 24 hours, see BillingService.create_portal_session.
    assert fake.portal_calls == ["sub_existing"]


# --- BillingService: webhook handling ------------------------------------------------


def test_webhook_subscription_created_links_business_and_sets_trial(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    payload = _subscription_event(
        "subscription_created",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_PRO,
        status="on_trial",
        trial_ends_at="2024-01-08T00:00:00.000000Z",
        renews_at="2024-01-08T00:00:00.000000Z",
        custom_data={"business_id": "acme-co", "plan": "pro"},
    )

    service.handle_webhook(payload, _sign(payload))

    business = service.get_status("acme-co")
    assert business.payment_customer_id == "cus_new"
    assert business.payment_subscription_id == "sub_new"
    assert business.plan == "pro"
    assert business.subscription_status == "on_trial"
    assert business.has_billing_access is True


def test_webhook_subscription_created_allows_shared_customer_id_across_businesses(uow_factory) -> None:
    """Regression test: found live in production when the same real person
    checked out for a *second* business under the same email -- Lemon
    Squeezy assigns one customer_id per email, not per subscription, so the
    second business's subscription_created event reused the first
    business's customer_id and used to blow up with an IntegrityError from
    the (former) unique index on payment_customer_id (see migration 0009).
    Every retry from Lemon Squeezy hit the same error, leaving the second
    business stuck on subscription_status="incomplete" forever with no
    visible error to the owner -- just a dashboard that silently never
    unlocked. business_id resolution itself was never the problem (it comes
    from custom_data, not customer_id -- see _resolve_business_id); this
    only exercises the write path that used to crash."""
    _make_business(uow_factory, "acme-co")
    _make_business(uow_factory, "acme-labs")
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())

    first = _subscription_event(
        "subscription_created",
        subscription_id="sub_acme_co",
        customer_id="cus_shared",
        variant_id=_VARIANT_STARTER,
        status="on_trial",
        trial_ends_at="2024-01-08T00:00:00.000000Z",
        renews_at="2024-01-08T00:00:00.000000Z",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    second = _subscription_event(
        "subscription_created",
        subscription_id="sub_acme_labs",
        customer_id="cus_shared",
        variant_id=_VARIANT_PRO,
        status="on_trial",
        trial_ends_at="2024-01-08T00:00:00.000000Z",
        renews_at="2024-01-08T00:00:00.000000Z",
        custom_data={"business_id": "acme-labs", "plan": "pro"},
    )

    service.handle_webhook(first, _sign(first))
    service.handle_webhook(second, _sign(second))  # used to raise IntegrityError

    acme_co = service.get_status("acme-co")
    acme_labs = service.get_status("acme-labs")
    assert acme_co.payment_customer_id == "cus_shared"
    assert acme_co.subscription_status == "on_trial"
    assert acme_labs.payment_customer_id == "cus_shared"
    assert acme_labs.plan == "pro"
    assert acme_labs.subscription_status == "on_trial"
    assert acme_labs.has_billing_access is True


def test_webhook_subscription_updated_sets_status_and_dates(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    payload = _subscription_event(
        "subscription_updated",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
        renews_at="2024-02-01T00:00:00.000000Z",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )

    service.handle_webhook(payload, _sign(payload))

    business = service.get_status("acme-co")
    assert business.subscription_status == "active"
    assert business.current_period_end is not None
    assert business.has_billing_access is True


def test_webhook_subscription_cancelled_still_grants_access(uow_factory) -> None:
    """Lemon Squeezy's `cancelled` means "the customer cancelled but the
    subscription is paid through ends_at" -- distinct from Stripe, where a
    separate cancel_at_period_end flag was needed. See ACTIVE_SUBSCRIPTION_STATUSES."""
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    created = _subscription_event(
        "subscription_created",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    service.handle_webhook(created, _sign(created))

    cancelled = _subscription_event(
        "subscription_cancelled",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="cancelled",
        ends_at="2024-03-01T00:00:00.000000Z",
    )
    service.handle_webhook(cancelled, _sign(cancelled))

    business = service.get_status("acme-co")
    assert business.subscription_status == "cancelled"
    assert business.has_billing_access is True
    assert business.current_period_end is not None


def test_webhook_subscription_expired_blocks_access(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    created = _subscription_event(
        "subscription_created",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    service.handle_webhook(created, _sign(created))

    expired = _subscription_event(
        "subscription_expired",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="expired",
        ends_at="2024-01-15T00:00:00.000000Z",
    )
    service.handle_webhook(expired, _sign(expired))

    business = service.get_status("acme-co")
    assert business.subscription_status == "expired"
    assert business.has_billing_access is False


def test_webhook_payment_failed_sets_past_due(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    created = _subscription_event(
        "subscription_created",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    service.handle_webhook(created, _sign(created))

    # subscription_payment_failed carries no custom_data -- must resolve via
    # the payment_customer_id already linked on the business.
    failed = _payment_failed_event(subscription_id="sub_new", customer_id="cus_new")
    service.handle_webhook(failed, _sign(failed))

    business = service.get_status("acme-co")
    assert business.subscription_status == "past_due"
    assert business.has_billing_access is False
    assert business.plan == "starter"  # carried over, not wiped by the invoice event


def test_webhook_bad_signature_rejected(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    payload = _subscription_event("subscription_created", subscription_id="sub_x", customer_id="cus_x")
    with pytest.raises(WebhookSignatureError):
        service.handle_webhook(payload, "not-the-right-signature")


def test_webhook_missing_signature_rejected(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    payload = _subscription_event("subscription_created", subscription_id="sub_x", customer_id="cus_x")
    with pytest.raises(WebhookSignatureError):
        service.handle_webhook(payload, None)


def test_webhook_malformed_payload_rejected(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    payload = b"not json"
    with pytest.raises(WebhookSignatureError):
        service.handle_webhook(payload, _sign(payload))


def test_webhook_unresolvable_business_is_a_noop(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    payload = _subscription_event(
        "subscription_updated", subscription_id="sub_orphan", customer_id="cus_never_seen", status="active"
    )
    service.handle_webhook(payload, _sign(payload))  # must not raise

    business = service.get_status("acme-co")
    assert business.subscription_status == "incomplete"  # untouched


def test_webhook_ignores_unhandled_event_types(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    payload = json.dumps({"meta": {"event_name": "order_created"}, "data": {"id": "order_1"}}).encode("utf-8")
    service.handle_webhook(payload, _sign(payload))  # must not raise


# --- BillingService: webhook duplicate / out-of-order protection --------------------


def test_webhook_duplicate_delivery_is_a_no_op(uow_factory) -> None:
    """A Lemon Squeezy retry resends the byte-identical body. Resending the
    very first subscription_created delivery -- arriving late, after the
    subscription was already cancelled -- must not revert the business back
    to on_trial. This is the exact production risk named in the task: an
    unconditional handler would happily reapply it."""
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    created = _subscription_event(
        "subscription_created",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="on_trial",
        trial_ends_at="2024-01-08T00:00:00.000000Z",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    service.handle_webhook(created, _sign(created))
    cancelled = _subscription_event(
        "subscription_cancelled",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="cancelled",
        ends_at="2024-02-01T00:00:00.000000Z",
    )
    service.handle_webhook(cancelled, _sign(cancelled))
    assert service.get_status("acme-co").subscription_status == "cancelled"

    # Lemon Squeezy retries the ORIGINAL created delivery (identical bytes).
    service.handle_webhook(created, _sign(created))

    business = service.get_status("acme-co")
    assert business.subscription_status == "cancelled"  # not reverted to on_trial


def test_webhook_stale_update_does_not_resurrect_access_after_cancelled(uow_factory) -> None:
    """A late, OLDER subscription_updated (distinct delivery, not a byte-
    identical retry -- dedup alone wouldn't catch this) must not undo a
    more recent subscription_cancelled."""
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    created = _subscription_event(
        "subscription_created",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="on_trial",
        updated_at="2024-01-01T00:00:00.000000Z",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    service.handle_webhook(created, _sign(created))
    cancelled = _subscription_event(
        "subscription_cancelled",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="cancelled",
        ends_at="2024-03-01T00:00:00.000000Z",
        updated_at="2024-01-03T00:00:00.000000Z",
    )
    service.handle_webhook(cancelled, _sign(cancelled))
    assert service.get_status("acme-co").subscription_status == "cancelled"

    # Delivered out of order: timestamped BEFORE the cancellation above, but
    # arrives at the server after it.
    stale_update = _subscription_event(
        "subscription_updated",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
        updated_at="2024-01-02T00:00:00.000000Z",
    )
    service.handle_webhook(stale_update, _sign(stale_update))

    business = service.get_status("acme-co")
    assert business.subscription_status == "cancelled"  # not reverted to active


def test_webhook_stale_update_does_not_resurrect_access_after_expired(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    created = _subscription_event(
        "subscription_created",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
        updated_at="2024-01-01T00:00:00.000000Z",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    service.handle_webhook(created, _sign(created))
    expired = _subscription_event(
        "subscription_expired",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="expired",
        ends_at="2024-01-15T00:00:00.000000Z",
        updated_at="2024-01-15T00:00:00.000000Z",
    )
    service.handle_webhook(expired, _sign(expired))
    assert service.get_status("acme-co").subscription_status == "expired"

    stale_update = _subscription_event(
        "subscription_updated",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
        updated_at="2024-01-10T00:00:00.000000Z",
    )
    service.handle_webhook(stale_update, _sign(stale_update))

    business = service.get_status("acme-co")
    assert business.subscription_status == "expired"  # not reverted to active
    assert business.has_billing_access is False


def test_webhook_newer_update_after_cancelled_still_applies(uow_factory) -> None:
    """The staleness guard must only block OLDER events -- a genuinely newer
    snapshot (e.g. the customer resubscribed) still needs to go through."""
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    cancelled = _subscription_event(
        "subscription_cancelled",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="cancelled",
        ends_at="2024-02-01T00:00:00.000000Z",
        updated_at="2024-01-03T00:00:00.000000Z",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    service.handle_webhook(cancelled, _sign(cancelled))
    assert service.get_status("acme-co").subscription_status == "cancelled"

    resumed = _subscription_event(
        "subscription_updated",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
        updated_at="2024-01-10T00:00:00.000000Z",
    )
    service.handle_webhook(resumed, _sign(resumed))

    assert service.get_status("acme-co").subscription_status == "active"


def test_webhook_missing_timestamp_fields_still_applies_conservatively(uow_factory) -> None:
    """Neither fixture here sets updated_at/created_at -- BillingService must
    handle that absence conservatively (apply, since there's nothing to
    compare against) rather than erroring or silently dropping the event."""
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    created = _subscription_event(
        "subscription_created",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="on_trial",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    service.handle_webhook(created, _sign(created))
    first_business = service.get_status("acme-co")
    assert first_business.subscription_status == "on_trial"
    assert first_business.billing_event_at is None
    updated = _subscription_event(
        "subscription_updated",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
    )
    service.handle_webhook(updated, _sign(updated))

    business = service.get_status("acme-co")
    assert business.subscription_status == "active"
    assert business.billing_event_at is None


def test_webhook_without_timestamp_cannot_override_existing_watermark(uow_factory, caplog) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    cancelled = _subscription_event(
        "subscription_cancelled",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="cancelled",
        ends_at="2024-03-01T00:00:00.000000Z",
        updated_at="2024-02-01T00:00:00.000000Z",
        custom_data={"business_id": "acme-co", "plan": "starter"},
    )
    service.handle_webhook(cancelled, _sign(cancelled))

    timestamp_less_active = _subscription_event(
        "subscription_updated",
        subscription_id="sub_new",
        customer_id="cus_new",
        variant_id=_VARIANT_STARTER,
        status="active",
        nonce="late-without-time",
    )
    service.handle_webhook(timestamp_less_active, _sign(timestamp_less_active))

    business = service.get_status("acme-co")
    assert business.subscription_status == "cancelled"
    assert business.billing_event_at is not None
    assert "billing_webhook_missing_timestamp_ignored" in caplog.text


# --- HTTP layer: gate + reachability -------------------------------------------------


@pytest.fixture
def billing_app(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'billing_api.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    settings = _billing_settings(database_url=database_url)
    application = create_app(settings=settings)
    fake = FakeLemonSqueezyClient()

    def _override_billing_service():
        container = application.state.container
        return BillingService(container.unit_of_work_factory, container.settings, client=fake)

    with TestClient(application, raise_server_exceptions=False) as client:
        application.dependency_overrides[get_billing_service] = _override_billing_service
        yield client, fake
    engine.dispose()


def _signup_and_onboard(client: TestClient) -> tuple[str, str]:
    signup = client.post("/api/v1/auth/signup", json={"email": "owner@example.com", "password": "correct horse battery"})
    token = signup.json()["token"]
    onboarding = client.post(
        "/api/v1/businesses",
        json={
            "business_name": "Acme Co",
            "industry": "Consulting",
            "tone": "Friendly & direct",
            "services": [{"name": "Consulting call", "questions": ["What do you need help with?"]}],
            "service_zip_codes": [],
            "enforce_service_area": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    business_id = onboarding.json()["business_id"]
    return token, business_id


def test_dashboard_blocked_before_subscription(billing_app) -> None:
    client, _fake = billing_app
    token, business_id = _signup_and_onboard(client)

    response = client.get(f"/api/v1/businesses/{business_id}/cases", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "subscription_inactive"


def test_settings_reachable_without_subscription(billing_app) -> None:
    client, _fake = billing_app
    token, business_id = _signup_and_onboard(client)

    response = client.get(f"/api/v1/businesses/{business_id}/dna", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


def test_dashboard_unblocked_after_checkout_webhook(billing_app) -> None:
    client, _fake = billing_app
    token, business_id = _signup_and_onboard(client)

    checkout = client.post(
        f"/api/v1/businesses/{business_id}/billing/checkout-session",
        json={"plan": "starter"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert checkout.status_code == 200
    assert checkout.json()["checkout_url"] == "https://checkout.lemonsqueezy.test/session"

    webhook_payload = _subscription_event(
        "subscription_created",
        subscription_id="sub_http_test",
        customer_id="cus_http_test",
        variant_id=_VARIANT_STARTER,
        status="on_trial",
        trial_ends_at="2024-01-08T00:00:00.000000Z",
        renews_at="2024-01-08T00:00:00.000000Z",
        custom_data={"business_id": business_id, "plan": "starter"},
    )
    webhook_response = client.post(
        "/api/v1/billing/webhook",
        content=webhook_payload,
        headers={"X-Signature": _sign(webhook_payload)},
    )
    assert webhook_response.status_code == 200

    dashboard_response = client.get(
        f"/api/v1/businesses/{business_id}/cases", headers={"Authorization": f"Bearer {token}"}
    )
    assert dashboard_response.status_code == 200

    status_response = client.get(
        f"/api/v1/businesses/{business_id}/billing", headers={"Authorization": f"Bearer {token}"}
    )
    assert status_response.json()["subscription_status"] == "on_trial"
    assert status_response.json()["has_billing_access"] is True

    duplicate_checkout = client.post(
        f"/api/v1/businesses/{business_id}/billing/checkout-session",
        json={"plan": "starter"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert duplicate_checkout.status_code == 409
    assert duplicate_checkout.json()["error"]["code"] == "billing_already_active"


def test_webhook_rejects_bad_signature_over_http(billing_app) -> None:
    client, _fake = billing_app
    payload = _subscription_event("subscription_created", subscription_id="sub_x", customer_id="cus_x")
    response = client.post(
        "/api/v1/billing/webhook",
        content=payload,
        headers={"X-Signature": "wrong"},
    )
    assert response.status_code == 400


def test_webhook_requires_signature_header(billing_app) -> None:
    client, _fake = billing_app
    response = client.post("/api/v1/billing/webhook", content=b"{}")
    assert response.status_code == 422
