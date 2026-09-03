from src.demand.domain.handoff import InquiryHandoff
from src.demand.engine.handoff_adapter import DemandHandoffError, FlywheelIntakeClient


def test_flywheel_intake_client_posts_handoff_json(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def read(self) -> bytes:
            return b'{"case_id":"case-1","current_state":"NEW_LEAD"}'

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data
        captured["content_type"] = request.get_header("Content-type")
        captured["secret"] = request.get_header("X-internal-task-secret")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("src.demand.engine.handoff_adapter.urllib.request.urlopen", fake_urlopen)
    client = FlywheelIntakeClient("https://flywheel.example", "secret-1")
    handoff = InquiryHandoff(
        business_id="acme-home-services",
        prospect_id="prospect-1",
        campaign_id="camp-1",
        channel="webchat",
        inquiry_text="I need a diagnostic visit",
    )
    result = client.deliver(handoff)
    assert result["case_id"] == "case-1"
    assert captured["url"].endswith("/api/v1/businesses/acme-home-services/demand/inquiries")
    assert captured["method"] == "POST"
    assert captured["secret"] == "secret-1"
    assert b"flywheel_demand" in captured["body"]


def test_flywheel_intake_client_wraps_http_errors(monkeypatch) -> None:
    import urllib.error
    from io import BytesIO

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            402,
            "Payment Required",
            hdrs={},
            fp=BytesIO(b'{"error":"demand_subscription_inactive"}'),
        )

    monkeypatch.setattr("src.demand.engine.handoff_adapter.urllib.request.urlopen", fake_urlopen)
    client = FlywheelIntakeClient("https://flywheel.example", "secret-1")
    handoff = InquiryHandoff(
        business_id="acme-home-services",
        prospect_id="prospect-1",
        campaign_id="camp-1",
        channel="webchat",
        inquiry_text="I need a diagnostic visit",
    )
    try:
        client.deliver(handoff)
    except DemandHandoffError as exc:
        assert "402" in str(exc)
    else:
        raise AssertionError("expected DemandHandoffError")
