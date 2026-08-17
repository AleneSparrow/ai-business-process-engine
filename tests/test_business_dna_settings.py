"""Unit tests for the Settings-page booking config added to BusinessDNASettingsService.

_apply() and SettingsUpdate are pure (no persistence), so these exercise them
directly without a UnitOfWork/DB -- see business_dna_settings_service.py.
"""

import pytest

from src.persistence.business_dna_settings_service import (
    BusinessDNASettingsService,
    SettingsServiceInput,
    SettingsUpdate,
)


def _base_config() -> dict:
    return {
        "business": {"id": "biz-1", "name": "Old Name", "industry": "Legal", "timezone": "UTC"},
        "communication": {"tone": "friendly"},
        "services": [
            {
                "id": "consultation",
                "name": "Consultation",
                "description": "Consultation",
                "duration_minutes": 60,
                "fulfillment_type": "human_review",
                "pricing": {"model": "custom_quote", "tax_included": False},
                "service_area_ids": ["primary"],
                "intake_keywords": ["consultation"],
                "booking_allowed": False,
                "qualification_questions": [],
            }
        ],
        "service_areas": [{"id": "primary", "type": "remote", "values": ["everywhere"]}],
        "qualification": {"enforce_service_area": False},
        "human_escalation": {"triggers": ["high", "emergency"]},
        "business_hours": {"monday": [{"opens": "09:00", "closes": "17:00"}]},
        "booking": {
            "enabled": False,
            "timezone": "UTC",
            "minimum_notice_minutes": 120,
            "maximum_advance_days": 60,
            "slot_interval_minutes": 30,
            "buffer_before_minutes": 15,
            "buffer_after_minutes": 15,
            "allowed_days": ["monday"],
            "allowed_times": [{"starts": "09:00", "ends": "17:00"}],
            "capacity": 1,
            "proposal_count": 3,
            "proposal_ttl_minutes": 30,
            "requires_confirmation": True,
            "cancellation_notice_hours": 24,
            "rescheduling": {"allowed": True, "minimum_notice_hours": 24},
            "cancellation": {"allowed": True, "minimum_notice_hours": 24},
        },
    }


def _update(**overrides) -> SettingsUpdate:
    defaults = dict(
        name="New Name",
        industry="Legal",
        tone="friendly",
        services=(SettingsServiceInput(id="consultation", name="Consultation", questions=()),),
        service_zip_codes=(),
        escalate_on_high_urgency=True,
        escalate_on_emergency=True,
    )
    defaults.update(overrides)
    return SettingsUpdate(**defaults)


def test_bookable_toggle_sets_fulfillment_type_and_booking_allowed():
    update = _update(
        services=(
            SettingsServiceInput(id="consultation", name="Consultation", questions=(), bookable=True),
        ),
        booking_enabled=True,
        booking_timezone="America/New_York",
    )
    config = BusinessDNASettingsService._apply(_base_config(), update)
    service = config["services"][0]
    assert service["fulfillment_type"] == "bookable"
    assert service["booking_allowed"] is True
    assert config["booking"]["enabled"] is True
    assert config["booking"]["timezone"] == "America/New_York"
    assert config["business"]["timezone"] == "America/New_York"


def test_unbookable_toggle_resets_to_human_review():
    config = _base_config()
    config["services"][0]["fulfillment_type"] = "bookable"
    config["services"][0]["booking_allowed"] = True
    update = _update(
        services=(
            SettingsServiceInput(id="consultation", name="Consultation", questions=(), bookable=False),
        ),
    )
    result = BusinessDNASettingsService._apply(config, update)
    service = result["services"][0]
    assert service["fulfillment_type"] == "human_review"
    assert service["booking_allowed"] is False


def test_business_hours_update_replaces_configured_days():
    update = _update(
        business_hours={
            "monday": (("08:00", "18:00"),),
            "tuesday": (("08:00", "18:00"),),
        },
    )
    config = BusinessDNASettingsService._apply(_base_config(), update)
    assert config["business_hours"] == {
        "monday": [{"opens": "08:00", "closes": "18:00"}],
        "tuesday": [{"opens": "08:00", "closes": "18:00"}],
    }
    # Widened to "no extra restriction" so business_hours alone governs.
    assert config["booking"]["allowed_days"] == [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    ]
    assert config["booking"]["allowed_times"] == [{"starts": "00:00", "ends": "23:59"}]


def test_no_business_hours_submitted_leaves_prior_hours_unchanged():
    config = BusinessDNASettingsService._apply(_base_config(), _update())
    assert config["business_hours"] == {"monday": [{"opens": "09:00", "closes": "17:00"}]}


def test_invalid_timezone_rejected():
    with pytest.raises(ValueError, match="timezone"):
        _update(booking_timezone="Mars/Olympus_Mons")


def test_business_hours_window_must_close_after_it_opens():
    with pytest.raises(ValueError, match="close after"):
        _update(business_hours={"monday": (("17:00", "09:00"),)})


def test_business_hours_rejects_unknown_day_key():
    with pytest.raises(ValueError, match="unrecognized day"):
        _update(business_hours={"someday": (("09:00", "17:00"),)})
