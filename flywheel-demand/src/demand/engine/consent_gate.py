"""Consent and CAN-SPAM / TCPA gates for loyalty sends."""

from __future__ import annotations

from typing import Mapping

from src.demand.domain.consent import ConsentChannel
from src.demand.domain.models import OutboundMessage, Prospect

UNSUBSCRIBE_LINE = "Reply STOP or use the unsubscribe link to opt out."
SMS_STOP_LINE = "Reply STOP to opt out."


class ConsentRequiredError(ValueError):
    """A loyalty send was blocked because permission is missing."""


class ComplianceFooterError(ValueError):
    """A commercial email is missing a required CAN-SPAM element."""


def required_channel(message: OutboundMessage) -> ConsentChannel:
    channel = message.channel.strip().casefold()
    if channel == ConsentChannel.SMS.value:
        return ConsentChannel.SMS
    if channel == ConsentChannel.EMAIL.value:
        return ConsentChannel.EMAIL
    raise ConsentRequiredError(f"loyalty sends only support email or sms, not {message.channel!r}")


def assert_can_send(
    prospect: Prospect,
    message: OutboundMessage,
    marketing_dna: Mapping[str, object],
) -> None:
    channel = required_channel(message)
    if not prospect.has_active_consent(channel):
        raise ConsentRequiredError(f"no active {channel.value} consent for prospect {prospect.prospect_id}")
    if channel is ConsentChannel.SMS and not (prospect.phone or "").strip():
        raise ConsentRequiredError("SMS send requires a phone number")
    if channel is ConsentChannel.EMAIL and not (prospect.email or "").strip():
        raise ConsentRequiredError("email send requires an email address")

    compliance = dict(marketing_dna.get("compliance") or {})
    if channel is ConsentChannel.EMAIL:
        address = str(compliance.get("physical_postal_address") or "").strip()
        if not address:
            raise ComplianceFooterError("CAN-SPAM requires a physical postal address before email sends")
        body = message.body
        if address not in body:
            raise ComplianceFooterError("commercial email must include the physical postal address")
        if "unsubscribe" not in body.casefold() and "opt out" not in body.casefold() and "opt-out" not in body.casefold():
            raise ComplianceFooterError("commercial email must include an unsubscribe method")
    if channel is ConsentChannel.SMS:
        if "STOP" not in message.body:
            raise ComplianceFooterError("marketing SMS must include STOP opt-out language")


def email_footer(marketing_dna: Mapping[str, object]) -> str:
    compliance = dict(marketing_dna.get("compliance") or {})
    address = str(compliance.get("physical_postal_address") or "").strip()
    if not address:
        raise ComplianceFooterError("CAN-SPAM requires a physical postal address before email sends")
    return f"\n\n{address}\n{UNSUBSCRIBE_LINE}"


def sms_footer() -> str:
    return f" {SMS_STOP_LINE}"
