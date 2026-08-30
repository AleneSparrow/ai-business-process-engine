"""Validation shared by webhook configuration and delivery."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit


AddressInfo = tuple[object, object, object, object, tuple[str, int] | tuple[str, int, int, int]]
Resolver = Callable[..., Iterable[AddressInfo]]


@dataclass(frozen=True, slots=True)
class ResolvedWebhookTarget:
    """A vetted DNS result that must be used for the subsequent connection."""

    hostname: str
    port: int
    addresses: tuple[str, ...]
    request_target: str
    host_header: str


def resolve_public_https_url(
    url: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> ResolvedWebhookTarget:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("webhook_url must be an absolute HTTPS URL without credentials or fragments")
    try:
        parsed_port = parsed.port
        port = 443 if parsed_port is None else parsed_port
        if not 1 <= port <= 65_535:
            raise ValueError("webhook_url port is outside the valid range")
        addresses = tuple(dict.fromkeys(item[4][0] for item in resolver(parsed.hostname, port)))
    except (OSError, ValueError) as exc:
        raise ValueError("webhook_url host could not be resolved") from exc
    if not addresses:
        raise ValueError("webhook_url host did not resolve to an address")
    try:
        non_global = any(not ipaddress.ip_address(address).is_global for address in addresses)
    except ValueError as exc:
        raise ValueError("webhook_url host resolved to an invalid address") from exc
    if non_global:
        raise ValueError("webhook_url must not resolve to a private or local address")
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    host_header = parsed.hostname if port == 443 else f"{parsed.hostname}:{port}"
    return ResolvedWebhookTarget(parsed.hostname, port, addresses, request_target, host_header)


def validate_public_https_url(url: str, *, resolver: Resolver = socket.getaddrinfo) -> None:
    """Validate configuration without retaining its destination details."""
    resolve_public_https_url(url, resolver=resolver)
