"""Self-serve Stripe billing: BillingService directly (fake Stripe client --
see FakeStripe below) plus the HTTP layer (billing routes, the
require_active_subscription gate on the dashboard, and that Settings/Business
DNA stay reachable regardless of subscription status).

The real `stripe` package is never imported here -- BillingService takes an
injectable `stripe_client`, so these tests exercise all of this module's own
logic (checkout/portal params, webhook event routing, business_id
resolution, status/date mapping) without needing Stripe installed or any
network access. See BillingService's docstring.
"""

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
    BillingAccountNotFoundError,
    BillingNotConfiguredError,
    InvalidPlanError,
    WebhookSignatureError,
)
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


# --- Fake Stripe client -------------------------------------------------------------


class SignatureVerificationError(Exception):
    pass


class _FakeError:
    SignatureVerificationError = SignatureVerificationError


class _RecordingResource:
    """Stands in for both `stripe.checkout.Session` and `stripe.billing_portal.Session`
    -- both are just "create(**kwargs) -> object with a url" from this module's
    point of view."""

    def __init__(self, url: str) -> None:
        self._url = url
        self.calls: list[dict] = []

    def create(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"id": "fake_id_123", "url": self._url}


class _FakeWebhook:
    def __init__(self, expected_secret: str) -> None:
        self.expected_secret = expected_secret

    def construct_event(self, payload: bytes, sig_header: str | None, secret: str) -> dict:
        if sig_header != "valid-signature" or secret != self.expected_secret:
            raise SignatureVerificationError("signature mismatch")
        return json.loads(payload)


class FakeStripe:
    def __init__(self, *, webhook_secret: str = "whsec_test") -> None:
        self.checkout = type("checkout", (), {})()
        self.checkout.Session = _RecordingResource("https://checkout.stripe.test/session")
        self.billing_portal = type("billing_portal", (), {})()
        self.billing_portal.Session = _RecordingResource("https://billing.stripe.test/portal")
        self.Webhook = _FakeWebhook(webhook_secret)
        self.error = _FakeError()


def _billing_settings(**overrides) -> Settings:
    defaults = dict(
        database_url="sqlite+pysqlite:///:memory:",
        app_env="test",
        stripe_secret_key="sk_test_fake",
        stripe_webhook_secret="whsec_test",
        stripe_price_starter="price_starter_fake",
        stripe_price_pro="price_pro_fake",
        frontend_base_url="http://localhost:5173",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _event(event_type: str, obj: dict) -> bytes:
    return json.dumps({"type": event_type, "data": {"object": obj}}).encode("utf-8")


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


def test_checkout_session_new_customer_uses_owner_email(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeStripe()
    service = BillingService(uow_factory, _billing_settings(), stripe_client=fake)

    url = service.create_checkout_session("acme-co", "starter", "owner@example.com")

    assert url == "https://checkout.stripe.test/session"
    call = fake.checkout.Session.calls[0]
    assert call["customer_email"] == "owner@example.com"
    assert "customer" not in call
    assert call["client_reference_id"] == "acme-co"
    assert call["metadata"] == {"business_id": "acme-co", "plan": "starter"}
    assert call["subscription_data"]["trial_period_days"] == 7
    assert call["line_items"] == [{"price": "price_starter_fake", "quantity": 1}]


def test_checkout_session_reuses_existing_stripe_customer(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeStripe()
    service = BillingService(uow_factory, _billing_settings(), stripe_client=fake)
    with uow_factory() as unit_of_work:
        unit_of_work.businesses.update_billing(
            "acme-co",
            stripe_customer_id="cus_existing",
            stripe_subscription_id=None,
            plan=None,
            subscription_status="canceled",
            trial_ends_at=None,
            current_period_end=None,
            cancel_at_period_end=False,
        )
        unit_of_work.commit()

    service.create_checkout_session("acme-co", "pro", "owner@example.com")

    call = fake.checkout.Session.calls[0]
    assert call["customer"] == "cus_existing"
    assert "customer_email" not in call


def test_checkout_session_rejects_unknown_plan(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), stripe_client=FakeStripe())
    with pytest.raises(InvalidPlanError):
        service.create_checkout_session("acme-co", "enterprise", "owner@example.com")


def test_checkout_session_requires_billing_configured(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, Settings(database_url="sqlite+pysqlite:///:memory:", app_env="test"))
    with pytest.raises(BillingNotConfiguredError):
        service.create_checkout_session("acme-co", "starter", "owner@example.com")


def test_portal_session_requires_existing_customer(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), stripe_client=FakeStripe())
    with pytest.raises(BillingAccountNotFoundError):
        service.create_portal_session("acme-co")


def test_portal_session_returns_url_once_customer_exists(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeStripe()
    service = BillingService(uow_factory, _billing_settings(), stripe_client=fake)
    with uow_factory() as unit_of_work:
        unit_of_work.businesses.update_billing(
            "acme-co",
            stripe_customer_id="cus_existing",
            stripe_subscription_id="sub_existing",
            plan="starter",
            subscription_status="active",
            trial_ends_at=None,
            current_period_end=None,
            cancel_at_period_end=False,
        )
        unit_of_work.commit()

    url = service.create_portal_session("acme-co")

    assert url == "https://billing.stripe.test/portal"
    assert fake.billing_portal.Session.calls[0]["customer"] == "cus_existing"


# --- BillingService: webhook handling ------------------------------------------------


def test_webhook_checkout_completed_links_customer_and_sets_trialing(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeStripe()
    service = BillingService(uow_factory, _billing_settings(), stripe_client=fake)
    payload = _event("checkout.session.completed", {
        "customer": "cus_new",
        "subscription": "sub_new",
        "client_reference_id": "acme-co",
        "metadata": {"business_id": "acme-co", "plan": "pro"},
    })

    service.handle_webhook(payload, "valid-signature")

    business = service.get_status("acme-co")
    assert business.stripe_customer_id == "cus_new"
    assert business.stripe_subscription_id == "sub_new"
    assert business.plan == "pro"
    assert business.subscription_status == "trialing"
    assert business.has_billing_access is True


def test_webhook_subscription_updated_sets_status_and_dates(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeStripe()
    service = BillingService(uow_factory, _billing_settings(), stripe_client=fake)
    payload = _event("customer.subscription.updated", {
        "id": "sub_new",
        "customer": "cus_new",
        "status": "active",
        "metadata": {"business_id": "acme-co", "plan": "starter"},
        "trial_end": 1_700_000_000,
        "current_period_end": 1_702_000_000,
        "cancel_at_period_end": True,
    })

    service.handle_webhook(payload, "valid-signature")

    business = service.get_status("acme-co")
    assert business.subscription_status == "active"
    assert business.cancel_at_period_end is True
    assert business.trial_ends_at is not None
    assert business.current_period_end is not None
    assert business.has_billing_access is True


def test_webhook_subscription_deleted_blocks_access(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeStripe()
    service = BillingService(uow_factory, _billing_settings(), stripe_client=fake)
    service.handle_webhook(_event("checkout.session.completed", {
        "customer": "cus_new", "subscription": "sub_new",
        "metadata": {"business_id": "acme-co", "plan": "starter"},
    }), "valid-signature")

    service.handle_webhook(_event("customer.subscription.deleted", {
        "id": "sub_new", "customer": "cus_new",
        "metadata": {"business_id": "acme-co"},
        "status": "active",  # Stripe sends the pre-cancellation status here; force_status wins
    }), "valid-signature")

    business = service.get_status("acme-co")
    assert business.subscription_status == "canceled"
    assert business.has_billing_access is False


def test_webhook_payment_failed_sets_past_due(uow_factory) -> None:
    _make_business(uow_factory)
    fake = FakeStripe()
    service = BillingService(uow_factory, _billing_settings(), stripe_client=fake)
    service.handle_webhook(_event("checkout.session.completed", {
        "customer": "cus_new", "subscription": "sub_new",
        "metadata": {"business_id": "acme-co", "plan": "starter"},
    }), "valid-signature")

    # invoice.payment_failed has no business_id metadata -- must resolve via
    # the stripe_customer_id already linked on the business.
    service.handle_webhook(_event("invoice.payment_failed", {
        "customer": "cus_new",
    }), "valid-signature")

    business = service.get_status("acme-co")
    assert business.subscription_status == "past_due"
    assert business.has_billing_access is False
    assert business.plan == "starter"  # carried over, not wiped by the invoice event


def test_webhook_bad_signature_rejected(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), stripe_client=FakeStripe())
    payload = _event("checkout.session.completed", {"customer": "cus_x"})
    with pytest.raises(WebhookSignatureError):
        service.handle_webhook(payload, "not-the-right-signature")


def test_webhook_unresolvable_business_is_a_noop(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), stripe_client=FakeStripe())
    payload = _event("customer.subscription.updated", {
        "id": "sub_orphan", "customer": "cus_never_seen", "status": "active",
    })
    service.handle_webhook(payload, "valid-signature")  # must not raise

    business = service.get_status("acme-co")
    assert business.subscription_status == "incomplete"  # untouched


def test_webhook_ignores_unhandled_event_types(uow_factory) -> None:
    _make_business(uow_factory)
    service = BillingService(uow_factory, _billing_settings(), stripe_client=FakeStripe())
    payload = _event("customer.updated", {"id": "cus_x"})
    service.handle_webhook(payload, "valid-signature")  # must not raise


# --- HTTP layer: gate + reachability -------------------------------------------------


@pytest.fixture
def billing_app(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'billing_api.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    settings = _billing_settings(database_url=database_url)
    application = create_app(settings=settings)
    fake = FakeStripe()

    def _override_billing_service():
        container = application.state.container
        return BillingService(container.unit_of_work_factory, container.settings, stripe_client=fake)

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
    client, fake = billing_app
    token, business_id = _signup_and_onboard(client)

    checkout = client.post(
        f"/api/v1/businesses/{business_id}/billing/checkout-session",
        json={"plan": "starter"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert checkout.status_code == 200
    assert checkout.json()["checkout_url"] == "https://checkout.stripe.test/session"

    webhook_payload = _event("checkout.session.completed", {
        "customer": "cus_http_test",
        "subscription": "sub_http_test",
        "metadata": {"business_id": business_id, "plan": "starter"},
    })
    webhook_response = client.post(
        "/api/v1/billing/webhook",
        content=webhook_payload,
        headers={"stripe-signature": "valid-signature"},
    )
    assert webhook_response.status_code == 200

    dashboard_response = client.get(
        f"/api/v1/businesses/{business_id}/cases", headers={"Authorization": f"Bearer {token}"}
    )
    assert dashboard_response.status_code == 200

    status_response = client.get(
        f"/api/v1/businesses/{business_id}/billing", headers={"Authorization": f"Bearer {token}"}
    )
    assert status_response.json()["subscription_status"] == "trialing"
    assert status_response.json()["has_billing_access"] is True


def test_webhook_rejects_bad_signature_over_http(billing_app) -> None:
    client, _fake = billing_app
    response = client.post(
        "/api/v1/billing/webhook",
        content=_event("checkout.session.completed", {"customer": "cus_x"}),
        headers={"stripe-signature": "wrong"},
    )
    assert response.status_code == 400


def test_webhook_requires_signature_header(billing_app) -> None:
    client, _fake = billing_app
    response = client.post("/api/v1/billing/webhook", content=b"{}")
    assert response.status_code == 422
