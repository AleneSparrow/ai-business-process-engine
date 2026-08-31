"""Real PostgreSQL proofs for BillingService's webhook duplicate/out-of-order
protection (see tests/test_billing.py for the SQLite-backed behavioral
coverage of the same feature; this file exercises the same guarantees under
genuine concurrent writers, where the Postgres-specific `ON CONFLICT DO
NOTHING` path in SQLAlchemyBillingWebhookEventRepository.claim actually
runs)."""

import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.config import Settings
from src.domain.tenancy import Business
from src.persistence.billing_service import BillingService
from src.persistence.sqlalchemy_models import BillingWebhookEventRow
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


pytestmark = pytest.mark.postgresql

_STORE_ID = "store_fake_1"
_VARIANT_STARTER = "variant_starter_fake"
_VARIANT_PRO = "variant_pro_fake"
_WEBHOOK_SECRET = "whsec_test"


class FakeLemonSqueezyClient:
    def create_checkout(self, **kwargs) -> dict:
        raise AssertionError("not used by these tests")

    def get_subscription(self, subscription_id: str) -> dict:
        raise AssertionError("not used by these tests")


@pytest.fixture(scope="module")
def pg_factory():
    url = os.getenv("TEST_DATABASE_URL")
    if not url or not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL")
    engine = create_database_engine(url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    yield factory
    engine.dispose()


def _billing_settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused/unused",
        app_env="test",
        lemonsqueezy_api_key="ls_test_fake",
        lemonsqueezy_webhook_secret=_WEBHOOK_SECRET,
        lemonsqueezy_store_id=_STORE_ID,
        lemonsqueezy_variant_starter=_VARIANT_STARTER,
        lemonsqueezy_variant_pro=_VARIANT_PRO,
        frontend_base_url="http://localhost:5173",
    )


def _sign(payload: bytes) -> str:
    return hmac.new(_WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _subscription_event(
    event_name: str,
    *,
    subscription_id: str,
    customer_id: str,
    status: str,
    updated_at: str | None = None,
    ends_at: str | None = None,
    custom_data: dict | None = None,
) -> bytes:
    attributes = {
        "customer_id": customer_id,
        "variant_id": _VARIANT_STARTER,
        "status": status,
        "ends_at": ends_at,
    }
    if updated_at is not None:
        attributes["updated_at"] = updated_at
    return json.dumps({
        "meta": {"event_name": event_name, "custom_data": custom_data or {}},
        "data": {"type": "subscriptions", "id": subscription_id, "attributes": attributes},
    }).encode("utf-8")


def _make_business(pg_factory, business_id: str) -> None:
    now = datetime.now(timezone.utc)
    with pg_factory() as uow:
        uow.businesses.add(Business(business_id, business_id, now, now))
        uow.commit()


def test_concurrent_identical_webhook_deliveries_apply_exactly_once(pg_factory) -> None:
    """Two threads racing to handle the SAME retried delivery (identical
    bytes, as Lemon Squeezy resends them) must not both apply it -- the
    unique constraint on event_fingerprint is the real guard being proven
    here, not application-level locking."""
    suffix = uuid4().hex
    business_id = f"pg-billing-dup-{suffix}"
    _make_business(pg_factory, business_id)
    service = BillingService(pg_factory, _billing_settings(), client=FakeLemonSqueezyClient())
    payload = _subscription_event(
        "subscription_created",
        subscription_id=f"sub-pg-dup-{suffix}",
        customer_id=f"cus-pg-dup-{suffix}",
        status="on_trial",
        custom_data={"business_id": business_id, "plan": "starter"},
    )
    signature = _sign(payload)
    barrier = Barrier(2)

    def deliver():
        barrier.wait(timeout=10)
        service.handle_webhook(payload, signature)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: deliver(), range(2)))

    with pg_factory() as uow:
        fingerprint_count = uow.session.scalar(
            select(func.count()).select_from(BillingWebhookEventRow).where(
                BillingWebhookEventRow.event_fingerprint == hashlib.sha256(payload).hexdigest()
            )
        )
    business = service.get_status(business_id)
    assert business.subscription_status == "on_trial"
    # Exactly one dedup row for this fingerprint, not two -- proves the
    # ON CONFLICT DO NOTHING path, not just "the end state happens to match".
    assert fingerprint_count == 1


def test_stale_out_of_order_update_does_not_resurrect_access_after_cancelled(pg_factory) -> None:
    suffix = uuid4().hex
    business_id = f"pg-billing-stale-{suffix}"
    _make_business(pg_factory, business_id)
    service = BillingService(pg_factory, _billing_settings(), client=FakeLemonSqueezyClient())

    created = _subscription_event(
        "subscription_created",
        subscription_id=f"sub-pg-stale-{suffix}",
        customer_id=f"cus-pg-stale-{suffix}",
        status="on_trial",
        updated_at="2024-01-01T00:00:00.000000Z",
        custom_data={"business_id": business_id, "plan": "starter"},
    )
    service.handle_webhook(created, _sign(created))

    cancelled = _subscription_event(
        "subscription_cancelled",
        subscription_id=f"sub-pg-stale-{suffix}",
        customer_id=f"cus-pg-stale-{suffix}",
        status="cancelled",
        ends_at="2024-03-01T00:00:00.000000Z",
        updated_at="2024-01-03T00:00:00.000000Z",
    )
    service.handle_webhook(cancelled, _sign(cancelled))
    assert service.get_status(business_id).subscription_status == "cancelled"

    stale_update = _subscription_event(
        "subscription_updated",
        subscription_id=f"sub-pg-stale-{suffix}",
        customer_id=f"cus-pg-stale-{suffix}",
        status="active",
        updated_at="2024-01-02T00:00:00.000000Z",
    )
    service.handle_webhook(stale_update, _sign(stale_update))

    business = service.get_status(business_id)
    assert business.subscription_status == "cancelled"
    assert business.has_billing_access is True
