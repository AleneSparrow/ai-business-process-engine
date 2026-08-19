"""Onboarding defaults -- see business_dna_builder.py for the live-traffic
finding (2026-08-19) that motivated the timezone default below."""

from src.domain.business_dna_builder import (
    OnboardingInput,
    OnboardingService,
    build_business_dna,
)


def _onboarding(**overrides: object) -> OnboardingInput:
    defaults: dict[object, object] = dict(
        business_id="riverside-home-repairs",
        business_name="Riverside Home Repairs",
        industry="Home services",
        tone="formal",
        services=(OnboardingService(name="Drain cleaning"),),
        service_zip_codes=("90210", "90211", "90212"),
    )
    defaults.update(overrides)
    return OnboardingInput(**defaults)  # type: ignore[arg-type]


def test_new_business_defaults_to_a_real_us_timezone_not_utc() -> None:
    """Live finding: every fresh business used to default to "UTC" on both
    `business.timezone` and `booking.timezone` (there is no timezone question
    in the onboarding wizard) -- which is not just wrong for a 100% US-market
    product, it also silently defeated Settings' timezone <select> (see
    Settings.tsx: a value with no matching <option> renders as the first
    option without actually being it), so slot times reached real customers
    in UTC even on a business whose Settings page appeared to already say
    Eastern. Neither field should ever come back as "UTC" for a new
    business."""
    dna = build_business_dna(_onboarding())

    assert dna["business"]["timezone"] == "America/New_York"
    assert dna["booking"]["timezone"] == "America/New_York"
    assert dna["business"]["timezone"] != "UTC"
    assert dna["booking"]["timezone"] != "UTC"
