"""Sanitize an untrusted browser-supplied IANA timezone.

SMS and other non-browser channels have no device timezone. Guessing from a
phone number is unreliable (VoIP, ported numbers, moves), so those
conversations keep the business timezone. This module only validates a value
the widget already collected from Intl.
"""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import available_timezones


@lru_cache(maxsize=1)
def _known_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def sanitize_customer_timezone(value: str | None) -> str | None:
    """Return a known IANA zone, or None. Never raises for junk input.

    A malformed browser value must not cost the business a lead: public
    conversation create stays 200 and display falls back to the business zone.
    Owner-entered booking_timezone is different and still 4xx on Settings save.
    """
    if value is None:
        return None
    text = value.strip()
    if not text or text not in _known_timezones():
        return None
    return text
