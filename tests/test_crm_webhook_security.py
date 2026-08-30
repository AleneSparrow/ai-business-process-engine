import socket
import ssl

import pytest

from src.persistence.crm_webhook_client import _PinnedHTTPSConnection, post_json
from src.persistence.crm_webhook_service import CrmWebhookService
from src.domain.models import utc_now
from src.domain.tenancy import Business
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine
from src.persistence.webhook_url_security import ResolvedWebhookTarget, validate_public_https_url


def resolver_for(address: str):
    def resolve(host: str, port: int):
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port))]
    return resolve


@pytest.mark.parametrize("url", (
    "http://hooks.example.com/path",
    "https://user:pass@hooks.example.com/path",
    "https://hooks.example.com/path#fragment",
    "https://hooks.example.com:0/path",
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

    def read(self) -> bytes:
        return b""

class _Connection:
    def __init__(self, target: ResolvedWebhookTarget, response: _Response) -> None:
        self.target = target
        self.response = response
        self.requests = []
        self.closed = False

    def request(self, method, target, body, headers):
        self.requests.append((method, target, body, headers))

    def getresponse(self):
        return self.response

    def close(self) -> None:
        self.closed = True


def test_client_pins_the_validated_dns_address_through_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    target = ResolvedWebhookTarget(
        hostname="hooks.example.com",
        port=443,
        addresses=("93.184.216.34",),
        request_target="/path",
        host_header="hooks.example.com",
    )
    connection = _PinnedHTTPSConnection(target, timeout=5)
    peer: list[tuple[tuple[str, int], float]] = []
    tls_names: list[str] = []

    class FakeContext:
        def wrap_socket(self, sock, *, server_hostname: str):
            tls_names.append(server_hostname)
            return sock

    monkeypatch.setattr(
        "src.persistence.crm_webhook_client.socket.create_connection",
        lambda address, timeout: peer.append((address, timeout)) or object(),
    )
    connection._context = FakeContext()  # type: ignore[assignment]

    connection.connect()

    assert peer == [(("93.184.216.34", 443), 5)]
    assert tls_names == ["hooks.example.com"]


def test_pinned_connection_keeps_default_certificate_and_hostname_validation() -> None:
    connection = _PinnedHTTPSConnection(
        ResolvedWebhookTarget("hooks.example.com", 443, ("93.184.216.34",), "/", "hooks.example.com"),
        timeout=5,
    )

    assert connection._context.verify_mode == ssl.CERT_REQUIRED
    assert connection._context.check_hostname is True


def test_client_uses_one_dns_result_even_if_a_subsequent_lookup_would_rebind() -> None:
    resolutions = 0
    connections: list[_Connection] = []

    def rebinding_resolver(host: str, port: int):
        nonlocal resolutions
        resolutions += 1
        address = "93.184.216.34" if resolutions == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    def factory(target: ResolvedWebhookTarget, timeout: float) -> _Connection:
        connection = _Connection(target, _Response(204))
        connections.append(connection)
        return connection

    delivered = post_json(
        "https://hooks.example.com/path",
        {"state": "QUALIFIED"},
        resolver=rebinding_resolver,
        connection_factory=factory,
    )

    assert delivered is True
    assert resolutions == 1
    assert connections[0].target.addresses == ("93.184.216.34",)
    assert connections[0].requests[0][3]["Host"] == "hooks.example.com"
    assert connections[0].closed is True


def test_client_rejects_http_redirect_without_following_it() -> None:
    connections: list[_Connection] = []

    def factory(target: ResolvedWebhookTarget, timeout: float) -> _Connection:
        connection = _Connection(target, _Response(302))
        connections.append(connection)
        return connection

    delivered = post_json(
        "https://hooks.example.com/path",
        {"state": "QUALIFIED"},
        resolver=resolver_for("93.184.216.34"),
        connection_factory=factory,
    )

    assert delivered is False
    assert len(connections) == 1
    assert len(connections[0].requests) == 1
