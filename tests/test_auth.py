"""Staff signup/login/session lifecycle and self-serve business creation."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from src.api.app import create_app
from src.config import Settings
from src.domain.account_security import _totp_code
from src.domain.models import utc_now
from src.persistence.password_reset_email import InMemoryPasswordResetEmailSender
from src.domain.business_dna_builder import OnboardingInput, OnboardingService, build_business_dna
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import create_database_engine


ROOT = Path(__file__).parents[1]


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


def signup(client: TestClient, email: str = "owner@example.com", password: str = "correct horse battery"):
    return client.post("/api/v1/auth/signup", json={"email": email, "password": password})


def onboarding_payload(name: str = "Ada's Plumbing") -> dict:
    return {
        "business_name": name,
        "industry": "Home services",
        "tone": "Friendly & direct",
        "services": [{"name": "Drain cleaning", "questions": ["Which drain is affected?"]}],
        "service_zip_codes": ["60601", "60602"],
        "enforce_service_area": True,
    }


def test_signup_returns_session_with_no_business_yet(auth_environment: TestClient) -> None:
    response = signup(auth_environment)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["business_id"] is None
    assert body["user"]["business_ids"] == []
    assert len(body["token"]) > 20


def test_signup_rejects_duplicate_email(auth_environment: TestClient) -> None:
    signup(auth_environment)
    response = signup(auth_environment)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


def test_signup_rejects_short_password(auth_environment: TestClient) -> None:
    response = auth_environment.post(
        "/api/v1/auth/signup", json={"email": "short@example.com", "password": "short"}
    )
    assert response.status_code == 422


def test_login_with_wrong_password_is_rejected(auth_environment: TestClient) -> None:
    signup(auth_environment, email="owner2@example.com")
    response = auth_environment.post(
        "/api/v1/auth/login", json={"email": "owner2@example.com", "password": "wrong password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_succeeds_with_correct_credentials(auth_environment: TestClient) -> None:
    signup(auth_environment, email="owner3@example.com", password="correct horse battery")
    response = auth_environment.post(
        "/api/v1/auth/login", json={"email": "owner3@example.com", "password": "correct horse battery"}
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "owner3@example.com"


def test_me_requires_authentication(auth_environment: TestClient) -> None:
    response = auth_environment.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_returns_current_user_with_valid_token(auth_environment: TestClient) -> None:
    token = signup(auth_environment, email="owner4@example.com").json()["token"]
    response = auth_environment.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "owner4@example.com"


def test_me_rejects_garbage_token(auth_environment: TestClient) -> None:
    response = auth_environment.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_logout_revokes_the_session(auth_environment: TestClient) -> None:
    token = signup(auth_environment, email="owner5@example.com").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    logout_response = auth_environment.post("/api/v1/auth/logout", headers=headers)
    assert logout_response.status_code == 204
    me_response = auth_environment.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 401


def test_forgot_password_response_is_neutral_and_reset_is_one_time(auth_environment: TestClient) -> None:
    original = signup(auth_environment, email="recover@example.com").json()["token"]
    known = auth_environment.post("/api/v1/auth/forgot-password", json={"email": "recover@example.com"})
    unknown = auth_environment.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    sender = auth_environment.app.state.container.password_reset_email_sender
    assert isinstance(sender, InMemoryPasswordResetEmailSender)
    token = sender.outbox[-1].reset_url.split("token=", 1)[1]
    reset = auth_environment.post("/api/v1/auth/reset-password", json={
        "token": token, "password": "a newly strong password 456",
    })
    assert reset.status_code == 204
    assert auth_environment.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {original}"}).status_code == 401
    assert auth_environment.post("/api/v1/auth/reset-password", json={
        "token": token, "password": "another strong password 789",
    }).status_code == 422


def test_two_factor_login_requires_separate_challenge(auth_environment: TestClient) -> None:
    signup_response = signup(auth_environment, email="twofactor@example.com")
    session_token = signup_response.json()["token"]
    headers = {"Authorization": f"Bearer {session_token}"}
    setup = auth_environment.post("/api/v1/auth/security/two-factor/setup", headers=headers, json={
        "current_password": "correct horse battery",
    })
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    code = _totp_code(secret, int(utc_now().timestamp()) // 30)
    confirm = auth_environment.post("/api/v1/auth/security/two-factor/confirm", headers=headers, json={"code": code})
    assert confirm.status_code == 200
    assert len(confirm.json()["codes"]) == 8

    login = auth_environment.post("/api/v1/auth/login", json={
        "email": "twofactor@example.com", "password": "correct horse battery",
    })
    assert login.status_code == 200
    assert login.json()["two_factor_required"] is True
    assert "token" not in login.json()
    challenge = login.json()["challenge_token"]
    complete = auth_environment.post(
        "/api/v1/auth/login/two-factor",
        headers={"X-Two-Factor-Challenge": challenge},
        json={"code": code},
    )
    assert complete.status_code == 200
    assert complete.json()["user"]["email"] == "twofactor@example.com"


def test_business_creation_requires_authentication(auth_environment: TestClient) -> None:
    response = auth_environment.post("/api/v1/businesses", json=onboarding_payload())
    assert response.status_code == 401


def test_business_creation_produces_schema_valid_dna_and_links_owner(auth_environment: TestClient) -> None:
    token = signup(auth_environment, email="owner6@example.com").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = auth_environment.post(
        "/api/v1/businesses", json=onboarding_payload("Ada's Plumbing Co"), headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["business_id"] in body["widget_snippet"]

    business_response = auth_environment.get(f"/api/v1/businesses/{body['business_id']}")
    assert business_response.status_code == 200

    me_response = auth_environment.get("/api/v1/auth/me", headers=headers)
    assert me_response.json()["business_id"] == body["business_id"]
    assert me_response.json()["business_ids"] == [body["business_id"]]


def test_account_can_create_multiple_businesses(auth_environment: TestClient) -> None:
    token = signup(auth_environment, email="owner7@example.com").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    first = auth_environment.post("/api/v1/businesses", json=onboarding_payload("First Co"), headers=headers)
    assert first.status_code == 201
    first_id = first.json()["business_id"]

    second = auth_environment.post("/api/v1/businesses", json=onboarding_payload("Second Co"), headers=headers)
    assert second.status_code == 201
    second_id = second.json()["business_id"]
    assert second_id != first_id

    # The account now has both -- the newest one is active, but both remain
    # accessible (this is what require_own_business gates on).
    me_response = auth_environment.get("/api/v1/auth/me", headers=headers)
    me_body = me_response.json()
    assert me_body["business_id"] == second_id
    assert set(me_body["business_ids"]) == {first_id, second_id}

    for business_id in (first_id, second_id):
        settings_response = auth_environment.get(
            f"/api/v1/businesses/{business_id}/dna", headers=headers
        )
        assert settings_response.status_code == 200, business_id


def test_dna_settings_widget_snippet_is_an_absolute_url_to_this_deployment(auth_environment: TestClient) -> None:
    """widget_snippet is meant to be pasted into the *business's own* website
    -- a relative "/widget/widget.js" would resolve against that site's own
    origin and 404 there instead of loading this backend's widget (regression
    test for that bug, see _widget_embed_snippet in src/api/schemas.py)."""
    token = signup(auth_environment, email="owner7c@example.com").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    created = auth_environment.post(
        "/api/v1/businesses", json=onboarding_payload("Widget Snippet Co"), headers=headers
    )
    business_id = created.json()["business_id"]

    settings_response = auth_environment.get(
        f"/api/v1/businesses/{business_id}/dna", headers=headers
    )
    assert settings_response.status_code == 200
    snippet = settings_response.json()["widget_snippet"]
    assert f'data-business-id="{business_id}"' in snippet
    assert 'src="/widget/widget.js"' not in snippet
    assert re.search(r'src="https?://[^"]+/widget/widget\.js"', snippet)


def test_dna_settings_widget_snippet_uses_the_forwarded_scheme_behind_a_proxy(
    auth_environment: TestClient,
) -> None:
    """Live finding (2026-08-19): request.base_url alone reports the scheme
    of the connection *to this process*, not the public one -- on Railway
    (TLS terminates at the platform edge) that produced an http:// snippet
    even though Settings itself loads over https, which a real HTTPS site
    refuses to load as mixed content. resolve_public_api_base falls back to
    X-Forwarded-Proto when PUBLIC_API_BASE_URL isn't configured (as in this
    test environment) -- confirm it actually gets honored end to end."""
    token = signup(auth_environment, email="owner7d@example.com").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    created = auth_environment.post(
        "/api/v1/businesses", json=onboarding_payload("Proxy Scheme Co"), headers=headers
    )
    business_id = created.json()["business_id"]

    settings_response = auth_environment.get(
        f"/api/v1/businesses/{business_id}/dna",
        headers={**headers, "X-Forwarded-Proto": "https"},
    )
    assert settings_response.status_code == 200
    snippet = settings_response.json()["widget_snippet"]
    assert re.search(r'src="https://[^"]+/widget/widget\.js"', snippet)
    assert 'src="http://' not in snippet


def test_list_my_businesses_returns_every_linked_business(auth_environment: TestClient) -> None:
    token = signup(auth_environment, email="owner7b@example.com").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    auth_environment.post("/api/v1/businesses", json=onboarding_payload("Alpha Co"), headers=headers)
    auth_environment.post("/api/v1/businesses", json=onboarding_payload("Beta Co"), headers=headers)

    response = auth_environment.get("/api/v1/businesses", headers=headers)
    assert response.status_code == 200
    names = {entry["name"] for entry in response.json()}
    assert names == {"Alpha Co", "Beta Co"}


def test_business_not_linked_to_account_is_forbidden(auth_environment: TestClient) -> None:
    owner_a_token = signup(auth_environment, email="ownerC@example.com").json()["token"]
    owner_b_token = signup(auth_environment, email="ownerD@example.com").json()["token"]
    created = auth_environment.post(
        "/api/v1/businesses",
        json=onboarding_payload("Owner A's Business"),
        headers={"Authorization": f"Bearer {owner_a_token}"},
    )
    business_id = created.json()["business_id"]

    response = auth_environment.get(
        f"/api/v1/businesses/{business_id}/dna",
        headers={"Authorization": f"Bearer {owner_b_token}"},
    )
    assert response.status_code == 403


def test_duplicate_business_name_is_rejected(auth_environment: TestClient) -> None:
    token_a = signup(auth_environment, email="ownerA@example.com").json()["token"]
    token_b = signup(auth_environment, email="ownerB@example.com").json()["token"]
    first = auth_environment.post(
        "/api/v1/businesses",
        json=onboarding_payload("Shared Name Co"),
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert first.status_code == 201
    second = auth_environment.post(
        "/api/v1/businesses",
        json=onboarding_payload("Shared Name Co"),
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "business_id_taken"


def test_generated_business_dna_validates_against_schema() -> None:
    onboarding = OnboardingInput(
        business_id="ada-plumbing",
        business_name="Ada's Plumbing",
        industry="Home services",
        tone="Friendly & direct",
        services=(OnboardingService("Drain cleaning", ("Which drain is affected?",)),),
        service_zip_codes=("60601", "60602"),
    )
    configuration = build_business_dna(onboarding)
    with (ROOT / "config" / "business_dna.schema.json").open(encoding="utf-8") as file:
        schema = json.load(file)
    Draft202012Validator(schema).validate(configuration)


def test_generated_business_dna_defaults_every_service_to_human_review() -> None:
    onboarding = OnboardingInput(
        business_id="ada-plumbing-2",
        business_name="Ada's Plumbing",
        industry="Home services",
        tone="Casual & brief",
        services=(OnboardingService("Furnace repair"), OnboardingService("AC repair")),
        service_zip_codes=("60601",),
    )
    configuration = build_business_dna(onboarding)
    assert all(service["fulfillment_type"] == "human_review" for service in configuration["services"])
    assert all(service["booking_allowed"] is False for service in configuration["services"])
