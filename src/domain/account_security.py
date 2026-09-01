"""Security primitives for staff-account recovery and TOTP.

All values returned by this module are short-lived credentials or one-time
recovery material.  Callers persist only their SHA-256 hashes, except the
TOTP seed which is authenticated-encrypted with an explicitly configured
server key.
"""

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken


def generate_one_time_token() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_counter(at: datetime, *, period_seconds: int = 30) -> int:
    if at.tzinfo is None:
        raise ValueError("TOTP time must be timezone-aware")
    return int(at.timestamp()) // period_seconds


def _totp_code(secret: str, counter: int, *, digits: int = 6) -> str:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return f"{value:0{digits}d}"


def verify_totp(secret: str, code: str, at: datetime, *, window: int = 1) -> bool:
    normalized = code.replace(" ", "")
    if len(normalized) != 6 or not normalized.isdigit():
        return False
    counter = _totp_counter(at)
    return any(
        hmac.compare_digest(_totp_code(secret, counter + offset), normalized)
        for offset in range(-window, window + 1)
    )


def provisioning_uri(secret: str, email: str, *, issuer: str = "Flywheel") -> str:
    # The account's email is only returned to its authenticated owner during
    # setup; it is never persisted in security audit metadata or logs.
    from urllib.parse import quote

    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"


def generate_recovery_codes(*, count: int = 8) -> tuple[str, ...]:
    if count < 1:
        raise ValueError("recovery code count must be positive")
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return tuple("-".join(
        "".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2)
    ) for _ in range(count))


class SecretBox:
    """Authenticated storage for TOTP seeds using the maintained Fernet AEAD.

    The configured master value is first derived to a Fernet-compatible key;
    only authenticated ciphertext is persisted.  The master value must be a
    high-entropy deployment secret and is supplied only through
    ``ACCOUNT_SECURITY_ENCRYPTION_KEY``.
    """

    def __init__(self, master_key: str | None) -> None:
        if master_key is None or len(master_key.encode("utf-8")) < 32:
            raise ValueError("ACCOUNT_SECURITY_ENCRYPTION_KEY must contain at least 32 characters")
        material = master_key.encode("utf-8")
        derived_key = hmac.new(
            material, b"flywheel-account-security-fernet-v1", "sha256"
        ).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(derived_key))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
            raise ValueError("invalid encrypted security secret") from exc
