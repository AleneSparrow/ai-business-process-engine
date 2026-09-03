"""Staff signup, login, and session validation.

Sessions are bearer tokens: the raw token is returned to the caller exactly
once and only its SHA-256 hash is ever persisted, mirroring how anonymous
conversation tokens are already handled in `conversation_service.py`.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import hmac
from typing import Protocol
from uuid import uuid4

from src.domain.auth import (
    StaffSession,
    StaffUser,
    generate_session_token,
    hash_password,
    hash_session_token,
    normalize_email,
    verify_password,
)
from src.domain.account_security import (
    SecretBox,
    generate_one_time_token,
    generate_recovery_codes,
    generate_totp_secret,
    hash_secret,
    provisioning_uri,
    verify_totp,
)
from src.domain.models import utc_now

from .password_reset_email import DisabledPasswordResetEmailSender, PasswordResetEmailSender
from .repositories import (
    LoginChallenge,
    PasswordResetRecord,
    RecoveryCode,
    SecurityAuditEvent,
    SecurityCredentials,
    UnitOfWork,
)

DEFAULT_SESSION_TTL_HOURS = 720
PASSWORD_RESET_TTL_MINUTES = 30
TWO_FACTOR_CHALLENGE_TTL_MINUTES = 10
TWO_FACTOR_SETUP_TTL_MINUTES = 15


class AuthError(RuntimeError):
    """Base class for authentication failures with a safe, generic message."""


class EmailAlreadyRegisteredError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class SessionInvalidError(AuthError):
    pass


class SecondFactorRequiredError(AuthError):
    def __init__(self, challenge_token: str, *, expires_in_minutes: int) -> None:
        self.challenge_token = challenge_token
        self.expires_in_minutes = expires_in_minutes


class SecondFactorInvalidError(AuthError):
    pass


class PasswordResetInvalidError(AuthError):
    pass


class SecurityNotConfiguredError(AuthError):
    pass


class RequestRateLimiter(Protocol):
    def allow(self, key: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    token: str
    user: StaffUser
    expires_at_hours: int


@dataclass(frozen=True, slots=True)
class TwoFactorSetup:
    secret: str
    provisioning_uri: str
    expires_in_minutes: int


@dataclass(frozen=True, slots=True)
class SecuritySession:
    session_id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    current: bool


@dataclass(frozen=True, slots=True)
class SecurityAuditEntry:
    event_id: str
    event_type: str
    created_at: datetime
    metadata: dict[str, object]


class AuthService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        *,
        session_ttl_hours: int = DEFAULT_SESSION_TTL_HOURS,
        frontend_base_url: str | None = None,
        password_reset_email_sender: PasswordResetEmailSender | None = None,
        account_security_encryption_key: str | None = None,
        forgot_password_rate_limiter: RequestRateLimiter | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._session_ttl_hours = session_ttl_hours
        self._frontend_base_url = frontend_base_url.rstrip("/") if frontend_base_url else None
        self._password_reset_email_sender = password_reset_email_sender or DisabledPasswordResetEmailSender()
        self._secret_box = SecretBox(account_security_encryption_key) if account_security_encryption_key else None
        self._forgot_password_rate_limiter = forgot_password_rate_limiter

    def signup(self, email: str, plain_password: str) -> AuthenticatedSession:
        normalized = normalize_email(email)
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.staff_users.get_by_email(normalized) is not None:
                raise EmailAlreadyRegisteredError("An account with this email already exists")
            now = utc_now()
            user = StaffUser(
                user_id=str(uuid4()),
                email=email.strip(),
                normalized_email=normalized,
                password_hash=hash_password(plain_password),
                business_id=None,
                created_at=now,
            )
            unit_of_work.staff_users.add(user)
            session = self._issue_session(unit_of_work, user)
            unit_of_work.commit()
        return session

    def login(self, email: str, plain_password: str) -> AuthenticatedSession:
        normalized = normalize_email(email)
        with self._unit_of_work_factory() as unit_of_work:
            # Serialise reset replacement per account. This prevents two
            # concurrent requests from leaving two independently usable links.
            user = unit_of_work.staff_users.get_by_email(normalized, for_update=True)
            if user is None or not verify_password(plain_password, user.password_hash):
                raise InvalidCredentialsError("Email or password is incorrect")
            credentials = unit_of_work.staff_security.get_credentials(user.user_id)
            if credentials is not None and credentials.totp_secret_encrypted is not None:
                challenge_token = generate_one_time_token()
                now = utc_now()
                unit_of_work.staff_security.add_login_challenge(LoginChallenge(
                    str(uuid4()), user.user_id, hash_secret(challenge_token), now,
                    now + timedelta(minutes=TWO_FACTOR_CHALLENGE_TTL_MINUTES), None,
                ))
                unit_of_work.commit()
                raise SecondFactorRequiredError(
                    challenge_token, expires_in_minutes=TWO_FACTOR_CHALLENGE_TTL_MINUTES
                )
            session = self._issue_session(unit_of_work, user)
            unit_of_work.commit()
        return session

    def update_profile(self, user: StaffUser, name: str) -> StaffUser:
        normalized_name = " ".join(name.split())
        if not normalized_name or len(normalized_name) > 120:
            raise ValueError("name must be between 1 and 120 characters")
        with self._unit_of_work_factory() as unit_of_work:
            persisted = unit_of_work.staff_users.get(user.user_id)
            if persisted is None:
                raise SessionInvalidError("User no longer exists")
            updated = replace(persisted, name=normalized_name)
            unit_of_work.staff_users.save(updated)
            unit_of_work.commit()
        return updated

    def request_password_reset(self, email: str, *, request_ip: str | None) -> None:
        """Always returns normally: callers must not reveal account existence."""
        normalized = normalize_email(email)
        limiter = self._forgot_password_rate_limiter
        if limiter is not None:
            email_key = hash_secret(normalized)
            if not limiter.allow(f"password-reset-email:{email_key}"):
                return
            if request_ip and not limiter.allow(f"password-reset-ip:{request_ip}"):
                return
        # Without both an explicitly configured public URL and a sender there
        # is no safe delivery path.  Keep the same neutral response but don't
        # mint a credential that can never reach its owner.
        if self._frontend_base_url is None or isinstance(self._password_reset_email_sender, DisabledPasswordResetEmailSender):
            return
        with self._unit_of_work_factory() as unit_of_work:
            user = unit_of_work.staff_users.get_by_email(normalized)
            if user is None:
                return
            now = utc_now()
            token = generate_one_time_token()
            unit_of_work.staff_security.invalidate_resets(user.user_id, now)
            unit_of_work.staff_security.add_reset(PasswordResetRecord(
                str(uuid4()), user.user_id, hash_secret(token), now,
                now + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES), None,
            ))
            self._audit(unit_of_work, user.user_id, "PASSWORD_RESET_REQUESTED", now)
            unit_of_work.commit()
        # An email never goes out for a transaction that failed to persist.
        # A delivery failure is deliberately silent to the requester (account
        # enumeration protection); they can safely request another link.
        try:
            self._password_reset_email_sender.send(
                recipient_email=user.email,
                reset_url=f"{self._frontend_base_url}/reset-password?token={token}",
            )
        except Exception:  # noqa: BLE001 - never disclose account/delivery state
            return

    def reset_password(self, token: str, new_password: str) -> None:
        # Validate up front so a malformed password never consumes a token.
        new_hash = hash_password(new_password)
        with self._unit_of_work_factory() as unit_of_work:
            now = utc_now()
            record = unit_of_work.staff_security.get_reset_by_hash(hash_secret(token), for_update=True)
            if record is None or record.used_at is not None or record.expires_at <= now:
                raise PasswordResetInvalidError("Password reset link is invalid or expired")
            user = unit_of_work.staff_users.get(record.user_id)
            if user is None:
                raise PasswordResetInvalidError("Password reset link is invalid or expired")
            unit_of_work.staff_users.save(replace(user, password_hash=new_hash))
            unit_of_work.staff_security.mark_reset_used(record.reset_id, now)
            unit_of_work.staff_security.invalidate_resets(user.user_id, now)
            unit_of_work.staff_security.invalidate_login_challenges(user.user_id, now)
            revoked = unit_of_work.staff_sessions.revoke_all_for_user(user.user_id, now)
            self._audit(unit_of_work, user.user_id, "PASSWORD_RESET_COMPLETED", now)
            if revoked:
                self._audit(unit_of_work, user.user_id, "SESSIONS_REVOKED", now, {"count": revoked})
            unit_of_work.commit()

    def change_password(
        self, user: StaffUser, current_session_token: str, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")
        new_hash = hash_password(new_password)
        with self._unit_of_work_factory() as unit_of_work:
            now = utc_now()
            persisted = unit_of_work.staff_users.get(user.user_id)
            if persisted is None or not verify_password(current_password, persisted.password_hash):
                raise InvalidCredentialsError("Current password is incorrect")
            unit_of_work.staff_users.save(replace(persisted, password_hash=new_hash))
            unit_of_work.staff_security.invalidate_login_challenges(user.user_id, now)
            current = unit_of_work.staff_sessions.get_by_token_hash(hash_session_token(current_session_token))
            current_id = current.session_id if current is not None and current.user_id == user.user_id else None
            revoked = unit_of_work.staff_sessions.revoke_all_for_user(
                user.user_id, now, except_session_id=current_id
            )
            self._audit(unit_of_work, user.user_id, "PASSWORD_CHANGED", now)
            if revoked:
                self._audit(unit_of_work, user.user_id, "SESSIONS_REVOKED", now, {"count": revoked})
            unit_of_work.commit()

    def begin_two_factor_setup(self, user: StaffUser, current_password: str) -> TwoFactorSetup:
        box = self._require_secret_box()
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")
        now = utc_now()
        secret = generate_totp_secret()
        with self._unit_of_work_factory() as unit_of_work:
            persisted = unit_of_work.staff_users.get(user.user_id)
            existing = unit_of_work.staff_security.get_credentials(user.user_id, for_update=True)
            if persisted is None or not verify_password(current_password, persisted.password_hash):
                raise InvalidCredentialsError("Current password is incorrect")
            unit_of_work.staff_security.save_credentials(SecurityCredentials(
                user.user_id, existing.totp_secret_encrypted if existing else None, box.encrypt(secret),
                now + timedelta(minutes=TWO_FACTOR_SETUP_TTL_MINUTES),
                existing.two_factor_enabled_at if existing else None, now,
            ))
            self._audit(unit_of_work, user.user_id, "TWO_FACTOR_SETUP_STARTED", now)
            unit_of_work.commit()
        return TwoFactorSetup(secret, provisioning_uri(secret, user.email), TWO_FACTOR_SETUP_TTL_MINUTES)

    def confirm_two_factor_setup(self, user: StaffUser, code: str) -> tuple[str, ...]:
        box = self._require_secret_box()
        with self._unit_of_work_factory() as unit_of_work:
            now = utc_now()
            credentials = unit_of_work.staff_security.get_credentials(user.user_id, for_update=True)
            if credentials is None or credentials.pending_expires_at is None or credentials.pending_expires_at <= now or not credentials.pending_totp_secret_encrypted:
                raise SecondFactorInvalidError("Two-factor setup is no longer active")
            secret = box.decrypt(credentials.pending_totp_secret_encrypted)
            if not verify_totp(secret, code, now):
                raise SecondFactorInvalidError("Authenticator code is invalid")
            codes = generate_recovery_codes()
            unit_of_work.staff_security.save_credentials(SecurityCredentials(
                user.user_id, box.encrypt(secret), None, None, now, now,
            ))
            unit_of_work.staff_security.replace_recovery_codes(user.user_id, self._recovery_records(user.user_id, codes, now))
            self._audit(unit_of_work, user.user_id, "TWO_FACTOR_ENABLED", now)
            unit_of_work.commit()
            return codes

    def verify_two_factor_login(self, challenge_token: str, code: str) -> AuthenticatedSession:
        box = self._require_secret_box()
        with self._unit_of_work_factory() as unit_of_work:
            now = utc_now()
            challenge = unit_of_work.staff_security.get_login_challenge_by_hash(hash_secret(challenge_token), for_update=True)
            if challenge is None or challenge.consumed_at is not None or challenge.expires_at <= now:
                raise SecondFactorInvalidError("Two-factor challenge is invalid or expired")
            user = unit_of_work.staff_users.get(challenge.user_id)
            credentials = unit_of_work.staff_security.get_credentials(challenge.user_id, for_update=True)
            if user is None or credentials is None or not credentials.totp_secret_encrypted:
                raise SecondFactorInvalidError("Two-factor challenge is invalid or expired")
            method = self._verify_second_factor(unit_of_work, credentials, code, now, box)
            if method is None:
                raise SecondFactorInvalidError("Authenticator code is invalid")
            unit_of_work.staff_security.consume_login_challenge(challenge.challenge_id, now)
            if method == "recovery_code":
                self._audit(unit_of_work, user.user_id, "RECOVERY_CODE_USED", now)
            session = self._issue_session(unit_of_work, user)
            unit_of_work.commit()
            return session

    def disable_two_factor(self, user: StaffUser, current_password: str, code: str) -> None:
        box = self._require_secret_box()
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")
        with self._unit_of_work_factory() as unit_of_work:
            now = utc_now()
            persisted = unit_of_work.staff_users.get(user.user_id)
            credentials = unit_of_work.staff_security.get_credentials(user.user_id, for_update=True)
            if persisted is None or not verify_password(current_password, persisted.password_hash) or credentials is None:
                raise SecondFactorInvalidError("Two-factor verification failed")
            method = self._verify_second_factor(unit_of_work, credentials, code, now, box)
            if method is None:
                raise SecondFactorInvalidError("Two-factor verification failed")
            unit_of_work.staff_security.save_credentials(SecurityCredentials(user.user_id, None, None, None, None, now))
            unit_of_work.staff_security.replace_recovery_codes(user.user_id, ())
            if method == "recovery_code":
                self._audit(unit_of_work, user.user_id, "RECOVERY_CODE_USED", now)
            self._audit(unit_of_work, user.user_id, "TWO_FACTOR_DISABLED", now)
            unit_of_work.commit()

    def regenerate_recovery_codes(self, user: StaffUser, current_password: str, code: str) -> tuple[str, ...]:
        box = self._require_secret_box()
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")
        with self._unit_of_work_factory() as unit_of_work:
            now = utc_now()
            credentials = unit_of_work.staff_security.get_credentials(user.user_id, for_update=True)
            method = self._verify_second_factor(unit_of_work, credentials, code, now, box) if credentials else None
            if method is None:
                raise SecondFactorInvalidError("Two-factor verification failed")
            codes = generate_recovery_codes()
            unit_of_work.staff_security.replace_recovery_codes(user.user_id, self._recovery_records(user.user_id, codes, now))
            if method == "recovery_code":
                self._audit(unit_of_work, user.user_id, "RECOVERY_CODE_USED", now)
            self._audit(unit_of_work, user.user_id, "RECOVERY_CODES_REGENERATED", now)
            unit_of_work.commit()
            return codes

    def list_sessions(self, user: StaffUser, current_session_token: str) -> tuple[SecuritySession, ...]:
        current_hash = hash_session_token(current_session_token)
        with self._unit_of_work_factory() as unit_of_work:
            return tuple(SecuritySession(
                session.session_id, session.created_at, session.expires_at, session.revoked_at,
                hmac.compare_digest(session.token_hash, current_hash),
            ) for session in unit_of_work.staff_sessions.list_for_user(user.user_id))

    def revoke_session(self, user: StaffUser, session_id: str, current_session_token: str) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            session = unit_of_work.staff_sessions.get(session_id)
            if session is None or session.user_id != user.user_id:
                raise SessionInvalidError("Session was not found")
            if hmac.compare_digest(session.token_hash, hash_session_token(current_session_token)):
                raise SessionInvalidError("Use logout to end the current session")
            if session.revoked_at is None:
                now = utc_now()
                unit_of_work.staff_sessions.revoke(session_id, now)
                self._audit(unit_of_work, user.user_id, "SESSION_REVOKED", now)
                unit_of_work.commit()

    def revoke_other_sessions(self, user: StaffUser, current_session_token: str) -> int:
        with self._unit_of_work_factory() as unit_of_work:
            now = utc_now()
            current = unit_of_work.staff_sessions.get_by_token_hash(hash_session_token(current_session_token))
            count = unit_of_work.staff_sessions.revoke_all_for_user(
                user.user_id, now, except_session_id=current.session_id if current and current.user_id == user.user_id else None
            )
            if count:
                self._audit(unit_of_work, user.user_id, "SESSIONS_REVOKED", now, {"count": count})
            unit_of_work.commit()
            return count

    def security_status(self, user: StaffUser) -> tuple[bool, int]:
        with self._unit_of_work_factory() as unit_of_work:
            credentials = unit_of_work.staff_security.get_credentials(user.user_id)
            codes = unit_of_work.staff_security.list_recovery_codes(user.user_id)
            return bool(credentials and credentials.totp_secret_encrypted), sum(code.used_at is None for code in codes)

    def list_security_audit(self, user: StaffUser) -> tuple[SecurityAuditEntry, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            return tuple(SecurityAuditEntry(event.event_id, event.event_type, event.created_at, dict(event.metadata))
                         for event in unit_of_work.staff_security.list_audit_events(user.user_id))

    def logout(self, token: str) -> None:
        token_hash = hash_session_token(token)
        with self._unit_of_work_factory() as unit_of_work:
            session = unit_of_work.staff_sessions.get_by_token_hash(token_hash)
            if session is not None and session.revoked_at is None:
                unit_of_work.staff_sessions.revoke(session.session_id, utc_now())
            unit_of_work.commit()

    def authenticate(self, token: str) -> StaffUser:
        token_hash = hash_session_token(token)
        with self._unit_of_work_factory() as unit_of_work:
            session = unit_of_work.staff_sessions.get_by_token_hash(token_hash)
            if session is None or not session.is_active(now=utc_now()):
                raise SessionInvalidError("Session is missing, expired, or revoked")
            user = unit_of_work.staff_users.get(session.user_id)
            if user is None:
                raise SessionInvalidError("Session refers to an unknown account")
            return user

    def _issue_session(self, unit_of_work: UnitOfWork, user: StaffUser) -> AuthenticatedSession:
        token = generate_session_token()
        now = utc_now()
        session = StaffSession(
            session_id=str(uuid4()),
            user_id=user.user_id,
            token_hash=hash_session_token(token),
            created_at=now,
            expires_at=now + timedelta(hours=self._session_ttl_hours),
        )
        unit_of_work.staff_sessions.add(session)
        return AuthenticatedSession(token, user, self._session_ttl_hours)

    def _require_secret_box(self) -> SecretBox:
        if self._secret_box is None:
            raise SecurityNotConfiguredError("Two-factor authentication is not configured on this deployment")
        return self._secret_box

    def _verify_second_factor(
        self, unit_of_work: UnitOfWork, credentials: SecurityCredentials, code: str, now, box: SecretBox
    ) -> str | None:
        if not credentials.totp_secret_encrypted:
            return None
        if verify_totp(box.decrypt(credentials.totp_secret_encrypted), code, now):
            return "totp"
        recovery = unit_of_work.staff_security.get_recovery_code(
            credentials.user_id, hash_secret(code.strip().upper()), for_update=True
        )
        if recovery is None:
            return None
        unit_of_work.staff_security.use_recovery_code(recovery.recovery_code_id, now)
        return "recovery_code"

    @staticmethod
    def _recovery_records(user_id: str, codes: tuple[str, ...], now) -> tuple[RecoveryCode, ...]:
        return tuple(RecoveryCode(str(uuid4()), user_id, hash_secret(code), now, None) for code in codes)

    @staticmethod
    def _audit(
        unit_of_work: UnitOfWork, user_id: str, event_type: str, now, metadata: dict[str, object] | None = None
    ) -> None:
        unit_of_work.staff_security.add_audit_event(SecurityAuditEvent(
            str(uuid4()), user_id, event_type, now, metadata or {},
        ))
