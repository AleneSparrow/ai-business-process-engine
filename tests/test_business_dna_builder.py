"""Onboarding defaults -- see business_dna_builder.py for the live-traffic
finding (2026-08-19) that motivated the timezone default below."""

import pytest

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
    business.

    Updated 2026-08-25. The guarantee this test exists for -- never "UTC", both
    fields agreeing -- is unchanged. What changed is the expected value: the
    zone is no longer one national constant but is derived from the ZIP codes
    the wizard already collects (src/domain/us_postal_timezones.py), because
    Eastern was wrong for most of the country and the zone is printed to the
    customer in every slot offer. This fixture serves 90210, so Pacific is the
    correct answer for it; asserting "America/New_York" here would be
    re-asserting the defect."""
    dna = build_business_dna(_onboarding())

    assert dna["business"]["timezone"] == "America/Los_Angeles"
    assert dna["booking"]["timezone"] == "America/Los_Angeles"
    assert dna["business"]["timezone"] != "UTC"
    assert dna["booking"]["timezone"] != "UTC"


@pytest.mark.parametrize(
    ("preset", "expected"),
    (
        ("Friendly & direct", "friendly, direct, and concise"),
        ("Formal & precise", "formal, precise, and professional"),
        ("Casual & brief", "casual, brief, and plainspoken"),
    ),
)
def test_customer_voice_presets_create_distinct_promptable_business_tones(
    preset: str,
    expected: str,
) -> None:
    dna = build_business_dna(_onboarding(tone=preset))

    assert dna["communication"]["tone"] == expected


def test_onboarding_ships_a_sales_opening_built_from_the_business_itself() -> None:
    dna = build_business_dna(_onboarding())

    pitch = dna["sales"]["opening_pitch"]
    assert "Riverside Home Repairs" in pitch
    assert "Drain cleaning" in pitch
    assert "Tell me what you're trying to get done" in pitch
    assert dna["chat_widget"]["welcome_message"].startswith("Hi — this is Riverside Home Repairs")
