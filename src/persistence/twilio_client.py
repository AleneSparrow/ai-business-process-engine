"""Minimal Twilio REST client (SMS + phone number provisioning) and inbound
webhook signature validation.

Deliberately stdlib-only (`urllib.request`, `hmac`, `hashlib`, `base64`) --
same convention as `lemonsqueezy_client.py`: Twilio's official Python SDK is
a real dependency for what amounts to three documented endpoints, and this
app has no PyPI access to install it against in every environment anyway.

- https://www.twilio.com/docs/sms/api/message-resource
- https://www.twilio.com/docs/phone-numbers/api/availablephonenumberlocal-resource
- https://www.twilio.com/docs/phone-numbers/api/incomingphonenumber-resource
- https://www.twilio.com/docs/usage/webhooks/webhooks-security (signature validation)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_BASE_URL = "https://api.twilio.com/2010-04-01"
_TIMEOUT_SECONDS = 15


class TwilioAPIError(RuntimeError):
    """The Twilio API returned an error response, or was unreachable."""


class TwilioClient:
    def __init__(self, account_sid: str, auth_token: str) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token

    def _request(self, method: str, path: str, form_body: dict[str, str] | None = None) -> dict[str, Any]:
        data = urllib.parse.urlencode(form_body).encode("utf-8") if form_body is not None else None
        request = urllib.request.Request(f"{_BASE_URL}{path}", data=data, method=method)
        credentials = base64.b64encode(f"{self._account_sid}:{self._auth_token}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {credentials}")
        if data is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise TwilioAPIError(f"Twilio API returned {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TwilioAPIError(f"Twilio API unreachable: {exc.reason}") from exc

    def send_sms(self, *, from_number: str, to_number: str, body: str) -> str:
        """POST .../Messages.json -- returns the created message's SID."""
        response = self._request(
            "POST",
            f"/Accounts/{self._account_sid}/Messages.json",
            {"From": from_number, "To": to_number, "Body": body},
        )
        return str(response["sid"])

    def find_available_us_number(self) -> str | None:
        """GET .../AvailablePhoneNumbers/US/Local.json -- returns one
        available SMS-enabled US number, or None if none are available
        (Twilio account out of search results / trial restrictions)."""
        query = urllib.parse.urlencode({"SmsEnabled": "true", "PageSize": "1"})
        response = self._request(
            "GET",
            f"/Accounts/{self._account_sid}/AvailablePhoneNumbers/US/Local.json?{query}",
        )
        numbers = response.get("available_phone_numbers", [])
        return str(numbers[0]["phone_number"]) if numbers else None

    def purchase_phone_number(self, *, phone_number: str, sms_webhook_url: str) -> str:
        """POST .../IncomingPhoneNumbers.json -- buys `phone_number` and
        points its inbound-SMS webhook at `sms_webhook_url`. Returns the
        purchased number's Twilio SID (needed to release it later, if ever)."""
        response = self._request(
            "POST",
            f"/Accounts/{self._account_sid}/IncomingPhoneNumbers.json",
            {"PhoneNumber": phone_number, "SmsUrl": sms_webhook_url, "SmsMethod": "POST"},
        )
        return str(response["sid"])


def validate_inbound_signature(
    auth_token: str,
    *,
    url: str,
    form_params: dict[str, str],
    signature: str,
) -> bool:
    """Verifies Twilio's `X-Twilio-Signature` header on an inbound webhook
    request, per https://www.twilio.com/docs/usage/webhooks/webhooks-security.
    `url` must be the exact URL Twilio requested (including scheme/host --
    Railway sits behind a proxy, so this must come from a trusted forwarded-
    host header, not request.url, or validation will always fail)."""
    payload = url + "".join(
        key + form_params[key] for key in sorted(form_params.keys())
    )
    computed = base64.b64encode(
        hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")
    return hmac.compare_digest(computed, signature)
