"""Inbound Twilio retries must not duplicate customer-facing replies."""

import base64
import hashlib
import hmac
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_container, get_intake_service, get_sms_service, get_sms_thread_service
from src.api.routes.sms import INBOUND_SMS_WEBHOOK_PATH, public_router
from src.config import Settings


class _FakeSmsService:
    def __init__(self) -> None:
        self.outbound_calls: list[tuple[str, str, str]] = []
        self.opt_outs: list[tuple[str, str, str]] = []
        self.opt_ins: list[tuple[str, str, str]] = []

    def resolve_business_id_by_phone(self, phone_number: str) -> str | None:
        return "tenant-a" if phone_number == "+15005550006" else None

    def send_outbound(self, business_id: str, *, to_number: str, body: str) -> str:
        self.outbound_calls.append((business_id, to_number, body))
        return "SM00000000000000000000000000000001"

    def enqueue_reply(
        self,
        business_id: str,
        *,
        to_number: str,
        body: str,
        inbound_message_id: str,
        ignore_suppression: bool = False,
    ) -> None:
        self.send_outbound(business_id, to_number=to_number, body=body)

    def opt_out(self, business_id: str, phone_number: str, *, inbound_message_id: str) -> None:
        self.opt_outs.append((business_id, phone_number, inbound_message_id))
        self.enqueue_reply(
            business_id,
            to_number=phone_number,
            body="You have been unsubscribed from texts from this number. Reply START to resume.",
            inbound_message_id=inbound_message_id,
            ignore_suppression=True,
        )

    def opt_in(self, business_id: str, phone_number: str, *, inbound_message_id: str) -> None:
        self.opt_ins.append((business_id, phone_number, inbound_message_id))

    def send_help(self, business_id: str, phone_number: str, *, inbound_message_id: str) -> None:
        self.enqueue_reply(
            business_id,
            to_number=phone_number,
            body="help",
            inbound_message_id=inbound_message_id,
            ignore_suppression=True,
        )


class _FakeThreads:
    def __init__(self) -> None:
        self.paused = False
        self.appended: list[tuple[str, str, str]] = []
        self.synced: list[str] = []

    def is_paused(self, business_id: str, phone_number: str) -> bool:
        return self.paused

    def append_customer_message(
        self, business_id: str, phone_number: str, *, body: str, inbound_message_id: str
    ) -> None:
        self.appended.append((phone_number, body, inbound_message_id))

    def sync_from_intake(
        self, business_id: str, phone_number: str, *, body: str, inbound_message_id: str, intake
    ) -> None:
        self.synced.append(inbound_message_id)


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


def _client(sms, intake, threads=None):
    auth_token = "twilio-test-token"
    public_base = "https://api.example.test"
    application = FastAPI()
    application.include_router(public_router)
    threads = threads or _FakeThreads()
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
    application.dependency_overrides[get_sms_thread_service] = lambda: threads
    return TestClient(application), auth_token, public_base, threads


def _post(client, auth_token, public_base, body: str, message_sid: str):
    form = {
        "From": "+15551234567",
        "To": "+15005550006",
        "Body": body,
        "MessageSid": message_sid,
    }
    signature = _signature(auth_token, f"{public_base}{INBOUND_SMS_WEBHOOK_PATH}", form)
    return client.post(INBOUND_SMS_WEBHOOK_PATH, data=form, headers={"X-Twilio-Signature": signature})


def test_duplicate_signed_twilio_webhook_sends_customer_reply_once() -> None:
    sms = _FakeSmsService()
    intake = _FakeIntakeService()
    client, auth_token, public_base, _threads = _client(sms, intake)
    with client:
        first = _post(client, auth_token, public_base, "I need help", "SM_inbound_once")
        duplicate = _post(client, auth_token, public_base, "I need help", "SM_inbound_once")

    assert first.status_code == duplicate.status_code == 200
    assert intake.received_ids == ["SM_inbound_once", "SM_inbound_once"]
    assert sms.outbound_calls == [("tenant-a", "+15551234567", "Thanks — what service do you need?")]


def test_stop_command_does_not_enter_intake() -> None:
    sms = _FakeSmsService()
    intake = _FakeIntakeService()
    client, auth_token, public_base, _threads = _client(sms, intake)
    with client:
        response = _post(client, auth_token, public_base, "STOP", "SM_stop")

    assert response.status_code == 200
    assert intake.received_ids == []
    assert sms.opt_outs == [("tenant-a", "+15551234567", "SM_stop")]
    assert sms.outbound_calls == [
        (
            "tenant-a",
            "+15551234567",
            "You have been unsubscribed from texts from this number. Reply START to resume.",
        )
    ]


def test_yes_is_not_treated_as_an_opt_in_command() -> None:
    sms = _FakeSmsService()
    intake = _FakeIntakeService()
    client, auth_token, public_base, _threads = _client(sms, intake)
    with client:
        response = _post(client, auth_token, public_base, "yes", "SM_yes")

    assert response.status_code == 200
    assert intake.received_ids == ["SM_yes"]
    assert sms.opt_ins == []


def test_paused_thread_does_not_run_intake() -> None:
    sms = _FakeSmsService()
    intake = _FakeIntakeService()
    threads = _FakeThreads()
    threads.paused = True
    client, auth_token, public_base, _ = _client(sms, intake, threads)
    with client:
        response = _post(client, auth_token, public_base, "still waiting", "SM_paused")

    assert response.status_code == 200
    assert intake.received_ids == []
    assert sms.outbound_calls == []
    assert threads.appended == [("+15551234567", "still waiting", "SM_paused")]
