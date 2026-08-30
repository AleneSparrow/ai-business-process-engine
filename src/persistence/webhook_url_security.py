"""Validation shared by webhook configuration and delivery."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlparse


AddressInfo = tuple[object, object, object, object, tuple[str, int] | tuple[str, int, int, int]]
Resolver = Callable[..., Iterable[AddressInfo]]


def validate_public_https_url(url: str, *, resolver: Resolver = socket.getaddrinfo) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("webhook_url must be an absolute HTTPS URL without credentials or fragments")
    try:
        addresses = {item[4][0] for item in resolver(parsed.hostname, parsed.port or 443)}
    except OSError as exc:
        raise ValueError("webhook_url host could not be resolved") from exc
    if not addresses:
        raise ValueError("webhook_url host did not resolve to an address")
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("webhook_url must not resolve to a private or local address")
