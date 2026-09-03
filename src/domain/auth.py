"""Dependency-free staff identity: users, sessions, and password hashing.

This becomes the real `approved_by` identity that the process engine's `HUMAN`
decision path has always required and audited (see `DecisionRouter`). No
credential material or raw session token is ever stored — only a salted
password hash and a SHA-256 hash of the session token, mirroring how public
conversation tokens are already handled.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime

from .models import _require_aware, _require_text

_PBKDF2_ALGORITHM = "sha256"
_PBKDF2_ITERATIONS = 390_000
_PBKDF2_SALT_BYTES = 16


def hash_password(plain_password: str) -> str:
    normalized = plain_password.strip()
    if len(plain_password) < 12 or not normalized:
        raise ValueError("password must be at least 12 non-whitespace characters")
    if normalized.casefold() in {"passwordpassword", "correcthorsebattery", "letmeinletmein"}:
        raise ValueError("password is too common")
    salt = secrets.token_hex(_PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGORITHM, plain_password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_{_PBKDF2_ALGORITHM}${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        algorithm_label, iterations_text, salt, expected_digest = password_hash.split("$")
        algorithm = algorithm_label.removeprefix("pbkdf2_")
        iterations = int(iterations_text)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.pbkdf2_hmac(
        algorithm, plain_password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return hmac.compare_digest(candidate, expected_digest)


def generate_session_token() -> str:
    """A high-entropy bearer token; only its SHA-256 hash is ever persisted."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().casefold()


@dataclass(frozen=True, slots=True)
class StaffUser:
    user_id: str
    email: str
    normalized_email: str
    password_hash: str
    business_id: str | None
    created_at: datetime
    business_ids: tuple[str, ...] = ()
    name: str | None = None
    """Every business this account is linked to (see `with_business`). An
    account may own more than one business -- `business_id` is just its
    currently active one, always a member of this set (or None if the set
    is empty)."""

    def __post_init__(self) -> None:
        _require_text(self.user_id, "user_id")
        _require_text(self.email, "email")
        _require_text(self.normalized_email, "normalized_email")
        _require_text(self.password_hash, "password_hash")
        _require_aware(self.created_at, "created_at")
        if self.name is not None:
            _require_text(self.name, "name")
        if self.business_id is not None and self.business_id not in self.business_ids:
            raise ValueError("business_id must be a member of business_ids")

    def with_business(self, business_id: str) -> "StaffUser":
        """Link the account to `business_id`, adding it to the account's set
        of businesses if it isn't already a member, and making it the
        account's active business. An account may be linked to any number
        of businesses -- this no longer rejects a second (or third...) one."""
        _require_text(business_id, "business_id")
        business_ids = (
            self.business_ids if business_id in self.business_ids else (*self.business_ids, business_id)
        )
        return StaffUser(
            self.user_id, self.email, self.normalized_email, self.password_hash,
            business_id, self.created_at, business_ids, self.name,
        )


@dataclass(frozen=True, slots=True)
class StaffSession:
    session_id: str
    user_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_text(self.session_id, "session_id")
        _require_text(self.user_id, "user_id")
        _require_text(self.token_hash, "token_hash")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.expires_at, "expires_at")
        if self.revoked_at is not None:
            _require_aware(self.revoked_at, "revoked_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")

    def is_active(self, *, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at
