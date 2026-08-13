"""Minimal Lemon Squeezy REST (JSON:API) client.

Deliberately built on the standard library (`urllib.request`) rather than a
third-party SDK or `requests`/`httpx` -- Lemon Squeezy doesn't ship an
official Python SDK, and the two calls this app actually needs (create a
checkout, fetch a subscription) don't justify a new dependency. Every method
here is a thin, direct mirror of one documented endpoint:

- https://docs.lemonsqueezy.com/api/checkouts/create-checkout
- https://docs.lemonsqueezy.com/api/subscriptions/the-subscription-object

See `BillingService` for how this is used and why it's injectable (tests pass
a fake in place of this class -- no network, no real API key needed).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

_BASE_URL = "https://api.lemonsqueezy.com/v1"
_TIMEOUT_SECONDS = 15


class LemonSqueezyAPIError(RuntimeError):
    """The Lemon Squeezy API returned an error response, or was unreachable."""


class LemonSqueezyClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(f"{_BASE_URL}{path}", data=data, method=method)
        request.add_header("Authorization", f"Bearer {self._api_key}")
        request.add_header("Accept", "application/vnd.api+json")
        if data is not None:
            request.add_header("Content-Type", "application/vnd.api+json")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise LemonSqueezyAPIError(f"Lemon Squeezy API returned {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LemonSqueezyAPIError(f"Lemon Squeezy API unreachable: {exc.reason}") from exc

    def create_checkout(
        self,
        *,
        store_id: str,
        variant_id: str,
        email: str,
        custom_data: dict[str, str],
        redirect_url: str,
    ) -> dict[str, Any]:
        """POST /v1/checkouts -- returns the full JSON:API response; the hosted
        checkout URL is at response["data"]["attributes"]["url"]. `custom_data`
        comes back in `meta.custom_data` on every related webhook event."""
        body = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "checkout_data": {"email": email, "custom": custom_data},
                    "product_options": {"redirect_url": redirect_url},
                },
                "relationships": {
                    "store": {"data": {"type": "stores", "id": str(store_id)}},
                    "variant": {"data": {"type": "variants", "id": str(variant_id)}},
                },
            }
        }
        return self._request("POST", "/checkouts", body)

    def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        """GET /v1/subscriptions/{id} -- used to fetch a *fresh* signed
        `urls.customer_portal` link (the one on a webhook payload expires after
        24 hours, so it can't just be stored from the original event)."""
        return self._request("GET", f"/subscriptions/{subscription_id}")
