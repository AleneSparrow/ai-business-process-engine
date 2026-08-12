"""Staff signup, login, and session validation.

Sessions are bearer tokens: the raw token is returned to the caller exactly
once and only its SHA-256 hash is ever persisted, mirroring how anonymous
conversation tokens are already handled in `conversation_service.py`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
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
from src.domain.models import utc_now

from .repositories import UnitOfWork

DEFAULT_SESSION_TTL_HOURS = 720


class AuthError(RuntimeError):
    """Base class for authentication failures with a safe, generic message."""


class EmailAlreadyRegisteredError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class SessionInvalidError(AuthError):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    token: str
    user: StaffUser
    expires_at_hours: int


class AuthService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        *,
        session_ttl_hours: int = DEFAULT_SESSION_TTL_HOURS,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._session_ttl_hours = session_ttl_hours

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
            user = unit_of_work.staff_users.get_by_email(normalized)
            if user is None or not verify_password(plain_password, user.password_hash):
                raise InvalidCredentialsError("Email or password is incorrect")
            session = self._issue_session(unit_of_work, user)
            unit_of_work.commit()
        return session

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
