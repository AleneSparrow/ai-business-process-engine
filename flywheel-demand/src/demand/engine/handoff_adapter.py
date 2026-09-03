"""Deliver a Demand inquiry to Flywheel over HTTP. No process-engine imports."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping, Protocol

from src.demand.domain.handoff import HANDOFF_ENTRY_STATE, InquiryHandoff


class InquiryDelivery(Protocol):
    def deliver(self, handoff: InquiryHandoff) -> Mapping[str, Any]: ...


class DemandHandoffError(RuntimeError):
    """Flywheel rejected or could not accept a Demand inquiry."""


class FlywheelIntakeClient:
    """POST /api/v1/businesses/{id}/demand/inquiries with the internal secret."""

    def __init__(self, api_base: str, internal_secret: str, *, timeout_seconds: float = 15.0) -> None:
        self._api_base = api_base.rstrip("/")
        self._internal_secret = internal_secret
        self._timeout_seconds = timeout_seconds

    def deliver(self, handoff: InquiryHandoff) -> dict[str, Any]:
        if handoff.entry_state != HANDOFF_ENTRY_STATE:
            raise DemandHandoffError("Demand may only hand off into NEW_LEAD")
        payload = json.dumps(handoff.to_intake_payload()).encode("utf-8")
        url = f"{self._api_base}/api/v1/businesses/{handoff.business_id}/demand/inquiries"
        request = urllib.request.Request(url, data=payload, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("X-Internal-Task-Secret", self._internal_secret)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise DemandHandoffError(f"Flywheel intake returned {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise DemandHandoffError(f"Flywheel intake unreachable: {exc.reason}") from exc
