import socket
import urllib.error

import pytest

from src.persistence.crm_webhook_client import _NoRedirect, post_json
from src.persistence.crm_webhook_service import CrmWebhookService
from src.domain.models import utc_now
from src.domain.tenancy import Business
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine
from src.persistence.webhook_url_security import validate_public_https_url


def resolver_for(address: str):
    def resolve(host: str, port: int):
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port))]
    return resolve


@pytest.mark.parametrize("url", (
    "http://hooks.example.com/path",
    "https://user:pass@hooks.example.com/path",
    "https://hooks.example.com/path#fragment",
))
def test_webhook_url_rejects_unsafe_shapes(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_https_url(url, resolver=resolver_for("93.184.216.34"))


@pytest.mark.parametrize("address", ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"))
def test_webhook_url_rejects_non_public_addresses(address: str) -> None:
    with pytest.raises(ValueError, match="private or local"):
        validate_public_https_url("https://hooks.example.com/path", resolver=resolver_for(address))


def test_webhook_url_rejects_mixed_public_and_private_dns_results() -> None:
    def mixed_resolver(host: str, port: int):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port)),
        ]

    with pytest.raises(ValueError, match="private or local"):
        validate_public_https_url("https://hooks.example.com/path", resolver=mixed_resolver)


def test_webhook_url_accepts_public_https_address() -> None:
    validate_public_https_url(
        "https://hooks.example.com/path?token=secret",
        resolver=resolver_for("93.184.216.34"),
    )


@pytest.fixture
def uow_factory(tmp_path):
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'crm-webhooks.db'}")
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    with factory() as unit_of_work:
        now = utc_now()
        unit_of_work.businesses.add(Business("tenant-a", "Tenant A", now, now))
        unit_of_work.commit()
    yield factory
    engine.dispose()


def test_rebinding_between_configuration_and_delivery_is_rejected(uow_factory) -> None:
    validation_calls: list[str] = []
    delivered: list[tuple[str, dict[str, object]]] = []

    def rebinding_validator(url: str) -> None:
        validation_calls.append(url)
        if len(validation_calls) == 2:
            raise ValueError("webhook_url must not resolve to a private or local address")

    service = CrmWebhookService(
        uow_factory,
        url_validator=rebinding_validator,
        webhook_poster=lambda url, payload: delivered.append((url, payload)) or True,
    )
    service.configure("tenant-a", "https://hooks.example.com/path")

    service.notify_if_configured("tenant-a", conversation_id="conversation-1", state="QUALIFIED")

    assert validation_calls == [
        "https://hooks.example.com/path",
        "https://hooks.example.com/path",
    ]
    assert delivered == []


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class _Opener:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response
        self.requests = []

    def open(self, request, *, timeout: int):
        self.requests.append((request, timeout))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def test_client_posts_to_a_validated_global_https_destination_without_network() -> None:
    validated: list[str] = []
    opener = _Opener(_Response(204))

    delivered = post_json(
        "https://hooks.example.com/path",
        {"state": "QUALIFIED"},
        url_validator=validated.append,
        opener_factory=lambda: opener,
    )

    assert delivered is True
    assert validated == ["https://hooks.example.com/path"]
    assert opener.requests[0][0].get_method() == "POST"


def test_client_rejects_http_redirect_without_following_it() -> None:
    assert _NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://other.example") is None
    redirect = urllib.error.HTTPError(
        "https://hooks.example.com/path", 302, "Found", {}, None
    )
    opener = _Opener(redirect)

    delivered = post_json(
        "https://hooks.example.com/path",
        {"state": "QUALIFIED"},
        url_validator=lambda _: None,
        opener_factory=lambda: opener,
    )

    assert delivered is False
    assert len(opener.requests) == 1
