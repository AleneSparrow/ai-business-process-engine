"""Inbound SMS command words the engine must not treat as a sales message.

Twilio and US carriers expect STOP / START / HELP as the *entire* message.
`YES` is intentionally not a start keyword: in this product a lone "yes"
accepts a quote or a slot.
"""

from __future__ import annotations

from typing import Literal

SmsCommand = Literal["stop", "start", "help"]

_STOP = frozenset({"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"})
_START = frozenset({"START", "UNSTOP"})
_HELP = frozenset({"HELP", "INFO"})


def classify_inbound_sms(body: str) -> SmsCommand | None:
    compact = "".join(body.strip().split()).upper()
    if not compact:
        return None
    if compact in _STOP:
        return "stop"
    if compact in _START:
        return "start"
    if compact in _HELP:
        return "help"
    return None
