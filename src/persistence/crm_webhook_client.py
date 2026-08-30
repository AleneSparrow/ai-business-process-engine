"""Minimal outbound webhook POST client for CRM sync (e.g. a Clio/Zapier/Make
catch hook).

Deliberately stdlib-only (`urllib.request`), same convention as
`lemonsqueezy_client.py` -- this is one POST call, doesn't justify a new
dependency. Unlike the Lemon Squeezy client, this NEVER raises: a CRM sync
notification is best-effort by design (see CrmWebhookService) and must never
be allowed to break the actual lead-to-sale flow it's reporting on.
"""

from __future__ import annotations

import json
import http.client
import socket
import ssl
from collections.abc import Callable
from typing import Any

from .webhook_url_security import ResolvedWebhookTarget, Resolver, resolve_public_https_url

_TIMEOUT_SECONDS = 5


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection whose TCP peer is a validated DNS result.

    The original hostname is still supplied to TLS for SNI and certificate
    hostname validation. This prevents DNS rebinding between validation and
    connect without weakening certificate verification.
    """

    def __init__(self, target: ResolvedWebhookTarget, *, timeout: float) -> None:
        self._connect_address = target.addresses[0]
        self._tls_hostname = target.hostname
        super().__init__(self._connect_address, target.port, timeout=timeout, context=ssl.create_default_context())

    def connect(self) -> None:
        self.sock = socket.create_connection((self._connect_address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self._tls_hostname)


ConnectionFactory = Callable[[ResolvedWebhookTarget, float], Any]


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    resolver: Resolver = socket.getaddrinfo,
    connection_factory: ConnectionFactory = lambda target, timeout: _PinnedHTTPSConnection(
        target, timeout=timeout
    ),
) -> bool:
    """POST `payload` as JSON to `url`. Returns True on a 2xx response, False
    on any failure (bad URL, network error, non-2xx status, timeout) -- never
    raises."""
    connection = None
    try:
        # The exact vetted address below is the TCP peer. Do not pass the
        # hostname to a client that might resolve it again after this check.
        target = resolve_public_https_url(url, resolver=resolver)
        data = json.dumps(payload).encode("utf-8")
        connection = connection_factory(target, _TIMEOUT_SECONDS)
        # http.client never follows redirects. Host remains the configured
        # hostname while TLS validates that hostname against the certificate.
        connection.request(
            "POST",
            target.request_target,
            body=data,
            headers={"Content-Type": "application/json", "Host": target.host_header},
        )
        response = connection.getresponse()
        response.read()
        return 200 <= response.status < 300
    except (http.client.HTTPException, OSError, ValueError, ssl.SSLError):
        return False
    finally:
        if connection is not None:
            connection.close()
