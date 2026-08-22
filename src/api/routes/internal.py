"""Operator-triggered internal tasks -- not part of the tenant-facing API.

Currently one endpoint: run a proactive stalled-lead follow-up sweep
(universal-sales-cycle-model.md section 8; see
src/persistence/follow_up_service.py for why this is an externally-
triggered sweep rather than an in-process background loop). No staff/tenant
auth applies here -- there is no "current business" for a platform-wide
sweep -- so a shared bearer secret (INTERNAL_TASK_SECRET) is the only guard.
Meant to be called by Alena manually (curl/Postman) or by a Railway Cron Job
hitting this URL on a schedule; if INTERNAL_TASK_SECRET is unset, the
endpoint refuses every request rather than running unauthenticated.
"""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from src.domain.models import utc_now
from src.persistence.follow_up_service import FollowUpSweepResult, PersistentFollowUpRunner
from src.persistence.sms_service import SmsService

from ..dependencies import ApplicationContainer, get_container
from ..errors import UnauthorizedError

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


def _require_task_secret(container: ApplicationContainer, provided: str | None) -> None:
    configured = container.settings.internal_task_secret
    if not configured:
        raise UnauthorizedError("Internal task endpoints are not enabled on this deployment")
    if not provided or not hmac.compare_digest(provided, configured):
        raise UnauthorizedError("Invalid or missing internal task secret")


@router.post(
    "/follow-up/run",
    summary="Run a proactive stalled-lead follow-up sweep across every business",
)
def run_follow_up_sweep(
    container: Annotated[ApplicationContainer, Depends(get_container)],
    x_internal_task_secret: Annotated[str | None, Header()] = None,
) -> dict[str, int]:
    _require_task_secret(container, x_internal_task_secret)
    sms_service = SmsService(
        container.unit_of_work_factory,
        account_sid=container.settings.twilio_account_sid,
        auth_token=container.settings.twilio_auth_token,
        public_api_base_url=container.settings.public_api_base_url,
    )
    runner = PersistentFollowUpRunner(container.unit_of_work_factory, sms_service)
    result: FollowUpSweepResult = runner.run(utc_now())
    return {
        "businesses_scanned": result.businesses_scanned,
        "cases_considered": result.cases_considered,
        "follow_ups_sent": result.follow_ups_sent,
        "follow_ups_skipped_stale": result.follow_ups_skipped_stale,
    }
