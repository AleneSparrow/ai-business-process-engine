"""First-touch attribution for staff signup.

This is an accounting record, not a claim of causality. The product stores
the first public landing (and optional UTM / referrer host) so founder GTM
does not fall back to last-click. Nothing here is shown on `/me`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping
from urllib.parse import urlparse

from .models import utc_now

_TOKEN = 64
_UTM = 128
_PATH = 200
_HOST = 253
_MAX_AGE = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class SignupAttribution:
    landing_path: str
    landing_from: str | None
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    referrer_host: str | None
    widget_opened: bool
    captured_at: datetime


def sanitize_signup_attribution(
    payload: Mapping[str, object] | None,
    *,
    now: datetime | None = None,
) -> SignupAttribution | None:
    """Drop empty or unsafe fields. Returns None when nothing usable remains."""
    if not payload:
        return None
    moment = now or utc_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    path = _landing_path(payload.get("landing_path"))
    landing_from = _token(payload.get("landing_from"), _TOKEN)
    utm_source = _token(payload.get("utm_source"), _UTM)
    utm_medium = _token(payload.get("utm_medium"), _UTM)
    utm_campaign = _token(payload.get("utm_campaign"), _UTM)
    referrer_host = _referrer_host(payload.get("referrer_host"))
    widget_opened = payload.get("widget_opened") is True
    captured_at = _captured_at(payload.get("captured_at"), moment)

    if (
        path == "/"
        and landing_from is None
        and utm_source is None
        and utm_medium is None
        and utm_campaign is None
        and referrer_host is None
        and not widget_opened
    ):
        return None
    return SignupAttribution(
        landing_path=path,
        landing_from=landing_from,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        referrer_host=referrer_host,
        widget_opened=widget_opened,
        captured_at=captured_at,
    )


def _landing_path(value: object) -> str:
    if not isinstance(value, str):
        return "/"
    stripped = value.strip()
    parsed = urlparse(stripped if "://" in stripped else f"https://ignored.example{stripped}")
    path = parsed.path or "/"
    if not path.startswith("/") or "://" in path or "\\" in path:
        return "/"
    if len(path) > _PATH:
        path = path[:_PATH]
    return path


def _token(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = "".join(ch for ch in value.strip().casefold() if ch.isalnum() or ch in "-_")
    if not cleaned:
        return None
    return cleaned[:limit]


def _referrer_host(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip().casefold()
    if not raw:
        return None
    host = urlparse(raw if "://" in raw else f"https://{raw}").hostname
    if not host or len(host) > _HOST or "@" in host:
        return None
    return host


def _captured_at(value: object, now: datetime) -> datetime:
    if isinstance(value, datetime):
        candidate = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return now
        candidate = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    else:
        return now
    if candidate > now + timedelta(minutes=5) or now - candidate > _MAX_AGE:
        return now
    return candidate
