"""Provider-agnostic delivery boundary for password-reset links.

No production provider is silently inferred.  Tests/dev can inject the
in-memory sender; production must wire an explicit sender implementation.
"""

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
import ssl
from typing import Protocol


class PasswordResetEmailSender(Protocol):
    def send(self, *, recipient_email: str, reset_url: str) -> None: ...


class DisabledPasswordResetEmailSender:
    """Safe default when no explicit production delivery adapter exists."""

    def send(self, *, recipient_email: str, reset_url: str) -> None:
        # Deliberately no logging: email + URL include PII and a bearer token.
        return None


class SmtpPasswordResetEmailSender:
    """Explicit TLS SMTP adapter; never logs recipient or reset URL."""
    def __init__(self, *, host: str, port: int, username: str, password: str, from_email: str, use_tls: bool) -> None:
        self._host, self._port, self._username, self._password, self._from_email, self._use_tls = host, port, username, password, from_email, use_tls

    def send(self, *, recipient_email: str, reset_url: str) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self._from_email, recipient_email, "Reset your Flywheel password"
        message.set_content(f"Reset your Flywheel password:\n{reset_url}\n\nThis link expires in 30 minutes and works once. If you did not request it, ignore this email.")
        with smtplib.SMTP(self._host, self._port, timeout=10) as client:
            if self._use_tls:
                client.starttls(context=ssl.create_default_context())
            client.login(self._username, self._password)
            client.send_message(message)


@dataclass(frozen=True, slots=True)
class PasswordResetEmail:
    recipient_email: str
    reset_url: str


class InMemoryPasswordResetEmailSender:
    """Test/development outbox. Never exposed through the HTTP API."""

    def __init__(self) -> None:
        self.outbox: list[PasswordResetEmail] = []

    def send(self, *, recipient_email: str, reset_url: str) -> None:
        self.outbox.append(PasswordResetEmail(recipient_email, reset_url))
