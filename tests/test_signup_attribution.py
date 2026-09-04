"""First-touch attribution at signup — sanitization and persistence."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import Settings
from src.domain.signup_attribution import sanitize_signup_attribution
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import create_database_engine


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def auth_environment(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'auth.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    application = create_app(settings=Settings(
        database_url=database_url,
        app_env="test",
        frontend_base_url="https://app.example.test",
        account_security_encryption_key="test-account-security-key-material-that-is-long-enough",
    ))
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client
    engine.dispose()


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def test_sanitize_keeps_utm_and_campaign_landing() -> None:
    record = sanitize_signup_attribution(
        {
            "landing_path": "/lawyers?utm_source=ignored",
            "landing_from": "LinkedIn",
            "utm_source": "linkedin",
            "utm_medium": "social",
            "utm_campaign": "wave1-ca",
            "referrer_host": "www.linkedin.com",
            "widget_opened": True,
            "captured_at": NOW.isoformat(),
        },
        now=NOW,
    )
    assert record is not None
    assert record.landing_path == "/lawyers"
    assert record.landing_from == "linkedin"
    assert record.utm_source == "linkedin"
    assert record.widget_opened is True
    assert record.referrer_host == "www.linkedin.com"


def test_sanitize_drops_empty_payload() -> None:
    assert sanitize_signup_attribution({}, now=NOW) is None
    assert sanitize_signup_attribution({"landing_path": "/", "widget_opened": False}, now=NOW) is None


def test_sanitize_strips_query_and_rejects_stale_capture() -> None:
    stale = NOW - timedelta(days=45)
    record = sanitize_signup_attribution(
        {
            "landing_path": "/signup",
            "landing_from": "home",
            "captured_at": stale.isoformat(),
        },
        now=NOW,
    )
    assert record is not None
    assert record.captured_at == NOW


def test_signup_without_attribution_still_creates_account(auth_environment: TestClient) -> None:
    response = auth_environment.post(
        "/api/v1/auth/signup",
        json={"email": "plain@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    user_id = response.json()["user"]["user_id"]
    with auth_environment.app.state.container.unit_of_work_factory() as unit_of_work:
        assert unit_of_work.staff_signup_attribution.get(user_id) is None


def test_signup_persists_first_touch_and_omits_it_from_me(auth_environment: TestClient) -> None:
    response = auth_environment.post(
        "/api/v1/auth/signup",
        json={
            "email": "attributed@example.com",
            "password": "correct horse battery",
            "attribution": {
                "landing_path": "/lawyers",
                "landing_from": "linkedin",
                "utm_source": "linkedin",
                "utm_medium": "social",
                "utm_campaign": "wave1",
                "referrer_host": "www.linkedin.com",
                "widget_opened": True,
                "captured_at": "2026-09-04T11:00:00+00:00",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert "attribution" not in body
    assert "attribution" not in body["user"]
    user_id = body["user"]["user_id"]
    token = body["token"]

    me = auth_environment.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert "attribution" not in me.json()

    with auth_environment.app.state.container.unit_of_work_factory() as unit_of_work:
        stored = unit_of_work.staff_signup_attribution.get(user_id)
    assert stored is not None
    assert stored.landing_path == "/lawyers"
    assert stored.landing_from == "linkedin"
    assert stored.utm_source == "linkedin"
    assert stored.widget_opened is True
    assert stored.referrer_host == "www.linkedin.com"


def test_new_business_dna_settings_expose_follow_up_schedule(auth_environment: TestClient) -> None:
    token = auth_environment.post(
        "/api/v1/auth/signup",
        json={"email": "followup-owner@example.com", "password": "correct horse battery"},
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    created = auth_environment.post(
        "/api/v1/businesses",
        json={
            "business_name": "Ada Consulting",
            "industry": "Consulting",
            "tone": "Friendly & direct",
            "services": [{"name": "Strategy call", "questions": ["What do you need help with?"]}],
            "service_zip_codes": [],
            "enforce_service_area": False,
        },
        headers=headers,
    )
    assert created.status_code == 201
    business_id = created.json()["business_id"]
    settings = auth_environment.get(f"/api/v1/businesses/{business_id}/dna", headers=headers)
    assert settings.status_code == 200
    body = settings.json()
    assert body["follow_up_delays_hours"] == [24, 72, 168]
    assert body["follow_up_maximum_attempts"] == 3
