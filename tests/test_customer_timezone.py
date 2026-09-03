from src.domain.customer_timezone import sanitize_customer_timezone


def test_known_iana_zone_is_kept() -> None:
    assert sanitize_customer_timezone("America/Los_Angeles") == "America/Los_Angeles"


def test_garbage_timezone_is_dropped() -> None:
    assert sanitize_customer_timezone("Not/A_Zone") is None
    assert sanitize_customer_timezone("  ") is None
    assert sanitize_customer_timezone(None) is None
