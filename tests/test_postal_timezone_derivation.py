"""A new business must quote appointment times in its own zone, not Eastern.

The zone reaches the customer directly: commercial_service renders slot offers
and booking confirmations with `%Z`, so it is printed in every "Choose an
appointment time" and every "Your appointment is confirmed for ...". Until
2026-08-25 every business created through the wizard was stamped
America/New_York regardless of the ZIP codes it had just entered, which put a
West Coast business three hours off in the first message a real customer ever
sees -- and only a separate trip to Settings fixed it, which is exactly the
per-business setup the product claims not to need.
"""

import pytest

from src.domain.business_dna_builder import (
    OnboardingInput,
    OnboardingService,
    build_business_dna,
)
from src.domain.us_postal_timezones import (
    DEFAULT_TIMEZONE,
    timezone_for_postal_code,
    timezone_for_service_area,
)


def _onboarding(**overrides: object) -> OnboardingInput:
    defaults: dict[object, object] = dict(
        business_id="zone-probe",
        business_name="Zone Probe",
        industry="Professional services",
        tone="formal",
        services=(OnboardingService(name="Consultation"),),
        service_zip_codes=("10001",),
    )
    defaults.update(overrides)
    return OnboardingInput(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("postal_code", "expected", "where"),
    (
        ("10001", "America/New_York", "Manhattan"),
        ("90210", "America/Los_Angeles", "Beverly Hills"),
        ("60601", "America/Chicago", "Chicago"),
        ("80202", "America/Denver", "Denver"),
        ("85001", "America/Phoenix", "Phoenix, no DST"),
        ("99501", "America/Anchorage", "Anchorage"),
        ("96813", "Pacific/Honolulu", "Honolulu"),
        ("73301", "America/Chicago", "Austin"),
        ("79901", "America/Denver", "El Paso -- Texas, but Mountain"),
        ("32501", "America/Chicago", "Pensacola -- Florida panhandle, Central"),
        ("33101", "America/New_York", "Miami -- the rest of Florida, Eastern"),
        ("83801", "America/Los_Angeles", "Idaho panhandle -- Pacific"),
        ("83702", "America/Denver", "Boise -- southern Idaho, Mountain"),
    ),
)
def test_known_postal_codes_resolve_to_the_right_zone(
    postal_code: str, expected: str, where: str
) -> None:
    """Includes the split-state cases, which are the whole reason for a table.

    A naive state-level mapping gets El Paso, the Florida panhandle and the
    Idaho panhandle wrong -- and those are the places where being wrong is
    least forgivable, because the neighbouring town really is in another zone.
    """
    assert timezone_for_postal_code(postal_code) == expected, where


def test_unplaceable_postal_code_keeps_the_previous_default() -> None:
    """Never worse than the constant it replaces."""
    assert timezone_for_postal_code("00000") is None
    assert timezone_for_service_area(("00000",)) == DEFAULT_TIMEZONE
    assert timezone_for_service_area(()) == DEFAULT_TIMEZONE
    assert timezone_for_service_area(None) == DEFAULT_TIMEZONE


def test_non_us_postal_code_falls_back_rather_than_guessing() -> None:
    """Market is US today; a UK or Canadian code must not be forced into a US zone."""
    assert timezone_for_postal_code("SW1A 1AA") is None
    assert timezone_for_postal_code("M5V 3L9") is None


def test_service_area_spanning_two_zones_takes_the_majority() -> None:
    """Real case: metro areas straddle zone lines (Chicago reaches into Indiana)."""
    assert timezone_for_service_area(("60601", "60602", "46320")) == "America/Chicago"


def test_new_business_gets_its_own_zone_not_eastern() -> None:
    dna = build_business_dna(_onboarding(service_zip_codes=("90210", "90211")))

    assert dna["business"]["timezone"] == "America/Los_Angeles"
    assert dna["booking"]["timezone"] == "America/Los_Angeles"


def test_business_and_booking_zones_never_disagree() -> None:
    """Two fields, one answer -- they are rendered by different code paths."""
    dna = build_business_dna(_onboarding(service_zip_codes=("80202",)))

    assert dna["business"]["timezone"] == dna["booking"]["timezone"]


def test_remote_business_keeps_the_documented_fallback() -> None:
    """No ZIP codes means no signal; the previous constant still applies.

    `enforce_service_area=False` is not incidental: OnboardingInput refuses an
    empty ZIP list while the service area is enforced, which is what a remote
    business actually looks like in the wizard ("Anywhere (remote)").
    """
    dna = build_business_dna(
        _onboarding(service_zip_codes=(), enforce_service_area=False)
    )

    assert dna["business"]["timezone"] == DEFAULT_TIMEZONE
