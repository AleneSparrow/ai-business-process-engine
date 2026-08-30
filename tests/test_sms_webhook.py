"""Inbound Twilio retries must not duplicate customer-facing replies."""

import base64
import hashlib
import hmac
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_container, get_intake_service, get_sms_service
from src.api.routes.sms import INBOUND_SMS_WEBHOOK_PATH, public_router
from src.config import Settings


class _FakeSmsService:
    def __init__(self) -> None:
        self.outbound_calls: list[tuple[str, str, str]] = []

    def resolve_business_id_by_phone(self, phone_number: str) -> str | None:
        return "tenant-a" if phone_number == "+15005550006" else None

    def send_outbound(self, business_id: str, *, to_number: str, body: str) -> str:
        self.outbound_calls.append((business_id, to_number, body))
        return "SM00000000000000000000000000000001"


class _FakeIntakeService:
    def __init__(self) -> None:
        self.received_ids: list[str] = []

    def receive(self, message):
        self.received_ids.append(message.external_message_id)
        return SimpleNamespace(
            response=SimpleNamespace(message_text="Thanks — what service do you need?"),
            duplicate=len(self.received_ids) > 1,
        )


def _signature(auth_token: str, url: str, form_params: dict[str, str]) -> str:
    text = url + "".join(key + form_params[key] for key in sorted(form_params))
    return base64.b64encode(hmac.new(auth_token.encode(), text.encode(), hashlib.sha1).digest()).decode()


def test_duplicate_signed_twilio_webhook_sends_customer_reply_once() -> None:
    auth_token = "twilio-test-token"
    public_base = "https://api.example.test"
    application = FastAPI()
    application.include_router(public_router)
    sms = _FakeSmsService()
    intake = _FakeIntakeService()
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        app_env="test",
        twilio_account_sid="AC_test",
        twilio_auth_token=auth_token,
        public_api_base_url=public_base,
    )
    application.dependency_overrides[get_container] = lambda: SimpleNamespace(settings=settings)
    application.dependency_overrides[get_sms_service] = lambda: sms
    application.dependency_overrides[get_intake_service] = lambda: intake
    form = {
        "From": "+15551234567",
        "To": "+15005550006",
        "Body": "I need help",
        "MessageSid": "SM_inbound_once",
    }
    signature = _signature(auth_token, f"{public_base}{INBOUND_SMS_WEBHOOK_PATH}", form)

    with TestClient(application) as client:
        first = client.post(INBOUND_SMS_WEBHOOK_PATH, data=form, headers={"X-Twilio-Signature": signature})
        duplicate = client.post(INBOUND_SMS_WEBHOOK_PATH, data=form, headers={"X-Twilio-Signature": signature})

    assert first.status_code == duplicate.status_code == 200
    assert intake.received_ids == ["SM_inbound_once", "SM_inbound_once"]
    assert sms.outbound_calls == [("tenant-a", "+15551234567", "Thanks — what service do you need?")]
