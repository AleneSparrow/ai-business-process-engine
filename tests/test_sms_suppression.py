"""STOP revokes follow-up consent and blocks later sends for that phone."""

from src.domain.models import Lead, utc_now
from src.domain.tenancy import Business
from src.persistence.sms_service import SmsService
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


def test_opt_out_revokes_consent_and_blocks_send(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'sms.db'}")
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    now = utc_now()
    with factory() as uow:
        uow.businesses.add(Business("tenant-a", "Tenant A", now, now))
        uow.leads.add(
            "tenant-a",
            Lead("lead-1", "Ada", None, "+15551234567", sms_consent=True),
            now,
        )
        uow.commit()

    sent: list[tuple[str, str]] = []

    class _Client:
        def send_sms(self, *, from_number: str, to_number: str, body: str) -> str:
            sent.append((to_number, body))
            return "SM1"

    service = SmsService(
        factory,
        account_sid="AC_test",
        auth_token="token",
        public_api_base_url="https://api.example.test",
    )
    service.get_number = lambda business_id: "+15005550006"  # type: ignore[method-assign]
    service._client = lambda: _Client()  # type: ignore[method-assign]

    service.opt_out("tenant-a", "+15551234567", inbound_message_id="SM_stop")

    with factory() as uow:
        lead = uow.leads.get("tenant-a", "lead-1")
        assert lead is not None
        assert lead.sms_consent is False
    assert service.is_suppressed("tenant-a", "+15551234567")
    assert sent == [
        (
            "+15551234567",
            "You have been unsubscribed from texts from this number. Reply START to resume.",
        )
    ]

    blocked = service.send_outbound("tenant-a", to_number="+15551234567", body="later")
    assert blocked is None
    assert sent == [
        (
            "+15551234567",
            "You have been unsubscribed from texts from this number. Reply START to resume.",
        )
    ]

    service.opt_in("tenant-a", "+15551234567", inbound_message_id="SM_start")
    assert service.is_suppressed("tenant-a", "+15551234567") is False
    with factory() as uow:
        lead = uow.leads.get("tenant-a", "lead-1")
        assert lead is not None
        assert lead.sms_consent is False

    engine.dispose()
