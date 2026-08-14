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
import urllib.error
import urllib.request
from typing import Any

_TIMEOUT_SECONDS = 5


def post_json(url: str, payload: dict[str, Any]) -> bool:
    """POST `payload` as JSON to `url`. Returns True on a 2xx response, False
    on any failure (bad URL, network error, non-2xx status, timeout) -- never
    raises."""
    try:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        return False
