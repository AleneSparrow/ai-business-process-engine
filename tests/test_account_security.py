"""Regression coverage for account recovery, TOTP, sessions, and audit privacy."""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from src.domain.account_security import _totp_code
from src.domain.models import utc_now
from src.persistence.auth_service import (
    AuthService,
    PasswordResetInvalidError,
    SecondFactorInvalidError,
    SecondFactorRequiredError,
)
from src.persistence.password_reset_email import InMemoryPasswordResetEmailSender
from src.persistence.sqlalchemy_models import (
    Base,
    StaffPasswordResetRow,
    StaffRecoveryCodeRow,
    StaffSecurityAuditEventRow,
)
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


_KEY = "test-account-security-key-material-that-is-long-enough"


@pytest.fixture
def security_environment(tmp_path: Path):
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'security.db'}")
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    sender = InMemoryPasswordResetEmailSender()
    service = AuthService(
        factory,
        frontend_base_url="https://app.example.test",
        password_reset_email_sender=sender,
        account_security_encryption_key=_KEY,
    )
    yield factory, service, sender
    engine.dispose()


def _reset_token(sender: InMemoryPasswordResetEmailSender) -> str:
    return sender.outbox[-1].reset_url.split("token=", 1)[1]


def test_forgot_password_is_neutral_and_stores_only_hash(security_environment) -> None:
    factory, service, sender = security_environment
    session = service.signup("owner@example.com", "a strong password 123")

    service.request_password_reset("owner@example.com", request_ip="127.0.0.1")
    service.request_password_reset("missing@example.com", request_ip="127.0.0.2")

    assert len(sender.outbox) == 1
    raw_token = _reset_token(sender)
    with factory() as uow:
        row = uow.session.scalar(select(StaffPasswordResetRow))
        assert row is not None
        assert raw_token not in row.token_hash
        assert row.user_id == session.user.user_id


def test_reset_is_one_time_and_revokes_every_session(security_environment) -> None:
    factory, service, sender = security_environment
    original = service.signup("owner@example.com", "a strong password 123")
    second = service.login("owner@example.com", "a strong password 123")
    service.request_password_reset("owner@example.com", request_ip="127.0.0.1")
    token = _reset_token(sender)

    service.reset_password(token, "another strong password 456")

    with pytest.raises(PasswordResetInvalidError):
        service.reset_password(token, "yet another strong password 789")
    with pytest.raises(Exception):
        service.authenticate(original.token)
    with pytest.raises(Exception):
        service.authenticate(second.token)
    assert service.authenticate(service.login("owner@example.com", "another strong password 456").token)
    with factory() as uow:
        events = uow.staff_security.list_audit_events(original.user.user_id)
    assert {event.event_type for event in events} >= {"PASSWORD_RESET_REQUESTED", "PASSWORD_RESET_COMPLETED", "SESSIONS_REVOKED"}


def test_change_password_requires_current_password_and_keeps_current_session(security_environment) -> None:
    _, service, _ = security_environment
    current = service.signup("owner@example.com", "a strong password 123")
    other = service.login("owner@example.com", "a strong password 123")

    with pytest.raises(Exception):
        service.change_password(current.user, current.token, "wrong password", "another strong password 456")
    service.change_password(current.user, current.token, "a strong password 123", "another strong password 456")

    assert service.authenticate(current.token).user_id == current.user.user_id
    with pytest.raises(Exception):
        service.authenticate(other.token)


def test_totp_login_requires_challenge_then_accepts_only_valid_code(security_environment) -> None:
    factory, service, _ = security_environment
    signup = service.signup("owner@example.com", "a strong password 123")
    setup = service.begin_two_factor_setup(signup.user, "a strong password 123")
    code = _totp_code(setup.secret, int(utc_now().timestamp()) // 30)
    recovery_codes = service.confirm_two_factor_setup(signup.user, code)
    assert len(recovery_codes) == 8

    with pytest.raises(SecondFactorRequiredError) as required:
        service.login("owner@example.com", "a strong password 123")
    with pytest.raises(SecondFactorInvalidError):
        service.verify_two_factor_login(required.value.challenge_token, "000000")
    # A failed attempt must not consume the still-valid short-lived challenge.
    session = service.verify_two_factor_login(required.value.challenge_token, code)
    assert session.user.user_id == signup.user.user_id
    with pytest.raises(SecondFactorInvalidError):
        service.verify_two_factor_login(required.value.challenge_token, code)

    with factory() as uow:
        codes = uow.session.scalars(select(StaffRecoveryCodeRow)).all()
        assert all(recovery.code_hash not in recovery_codes for recovery in codes)


def test_recovery_code_is_single_use_and_audited(security_environment) -> None:
    factory, service, _ = security_environment
    signup = service.signup("owner@example.com", "a strong password 123")
    setup = service.begin_two_factor_setup(signup.user, "a strong password 123")
    code = _totp_code(setup.secret, int(utc_now().timestamp()) // 30)
    recovery = service.confirm_two_factor_setup(signup.user, code)[0]
    with pytest.raises(SecondFactorRequiredError) as required:
        service.login("owner@example.com", "a strong password 123")
    service.verify_two_factor_login(required.value.challenge_token, recovery)
    with pytest.raises(SecondFactorRequiredError) as second:
        service.login("owner@example.com", "a strong password 123")
    with pytest.raises(SecondFactorInvalidError):
        service.verify_two_factor_login(second.value.challenge_token, recovery)
    with factory() as uow:
        events = uow.session.scalars(select(StaffSecurityAuditEventRow)).all()
        audit = [(event.event_type, event.metadata_json) for event in events]
    assert any(event_type == "RECOVERY_CODE_USED" for event_type, _ in audit)
    assert recovery not in repr(audit)


def test_security_sessions_and_audit_are_scoped_to_the_current_user(security_environment) -> None:
    _, service, _ = security_environment
    owner_a = service.signup("a@example.com", "a strong password 123")
    owner_b = service.signup("b@example.com", "b strong password 456")
    b_sessions = service.list_sessions(owner_b.user, owner_b.token)

    with pytest.raises(Exception):
        service.revoke_session(owner_a.user, b_sessions[0].session_id, owner_a.token)
    assert service.authenticate(owner_b.token).user_id == owner_b.user.user_id
    service.change_password(owner_a.user, owner_a.token, "a strong password 123", "a newer password 789")
    a_events = service.list_security_audit(owner_a.user)
    b_events = service.list_security_audit(owner_b.user)
    assert a_events and not b_events


def test_expired_pending_setup_does_not_enable_two_factor(security_environment) -> None:
    factory, service, _ = security_environment
    signup = service.signup("owner@example.com", "a strong password 123")
    setup = service.begin_two_factor_setup(signup.user, "a strong password 123")
    with factory() as uow:
        credentials = uow.staff_security.get_credentials(signup.user.user_id)
        assert credentials is not None
        uow.staff_security.save_credentials(credentials.__class__(
            credentials.user_id, credentials.totp_secret_encrypted,
            credentials.pending_totp_secret_encrypted, utc_now() - timedelta(seconds=1),
            credentials.two_factor_enabled_at, utc_now(),
        ))
        uow.commit()
    code = _totp_code(setup.secret, int(utc_now().timestamp()) // 30)
    with pytest.raises(SecondFactorInvalidError):
        service.confirm_two_factor_setup(signup.user, code)


def test_password_change_invalidates_pending_two_factor_challenge(security_environment) -> None:
    _, service, _ = security_environment
    signup = service.signup("owner@example.com", "a strong password 123")
    setup = service.begin_two_factor_setup(signup.user, "a strong password 123")
    code = _totp_code(setup.secret, int(utc_now().timestamp()) // 30)
    service.confirm_two_factor_setup(signup.user, code)
    with pytest.raises(SecondFactorRequiredError) as challenge:
        service.login("owner@example.com", "a strong password 123")

    service.change_password(
        signup.user, signup.token, "a strong password 123", "another strong password 456"
    )
    with pytest.raises(SecondFactorInvalidError):
        service.verify_two_factor_login(challenge.value.challenge_token, code)


def test_two_factor_setup_requires_current_password(security_environment) -> None:
    _, service, _ = security_environment
    signup = service.signup("owner@example.com", "a strong password 123")
    with pytest.raises(Exception):
        service.begin_two_factor_setup(signup.user, "wrong password")
