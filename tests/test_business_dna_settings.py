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
            SettingsServiceInput(id="consultation", name="Consultation", questions=(), commercial_path="booking"),
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
            SettingsServiceInput(id="consultation", name="Consultation", questions=(), commercial_path="human_review"),
        ),
    )
    result = BusinessDNASettingsService._apply(config, update)
    service = result["services"][0]
    assert service["fulfillment_type"] == "human_review"
    assert service["booking_allowed"] is False


def test_quote_path_sets_fixed_price_quoting():
    update = _update(
        services=(
            SettingsServiceInput(
                id="consultation", name="Consultation", questions=(), commercial_path="quote", quote_price="150"
            ),
        ),
    )
    config = BusinessDNASettingsService._apply(_base_config(), update)
    service = config["services"][0]
    assert service["fulfillment_type"] == "quote_required"
    assert service["booking_allowed"] is False
    assert service["quoting"] == {
        "pricing_type": "fixed",
        "automatic_quote_allowed": True,
        "required_pricing_inputs": [],
        "pricing_input_questions": {},
        "fixed_price": "150",
    }
    assert "direct_next_step_message" not in service


def test_quote_price_is_normalized_to_two_decimals():
    update = _update(
        services=(
            SettingsServiceInput(
                id="consultation", name="Consultation", questions=(), commercial_path="quote", quote_price="89.5"
            ),
        ),
    )
    config = BusinessDNASettingsService._apply(_base_config(), update)
    assert config["services"][0]["quoting"]["fixed_price"] == "89.5"


def test_quote_path_requires_price():
    with pytest.raises(ValueError, match="requires a price"):
        SettingsServiceInput(id="consultation", name="Consultation", questions=(), commercial_path="quote")


def test_quote_path_rejects_non_decimal_price():
    with pytest.raises(ValueError, match="decimal amount"):
        SettingsServiceInput(
            id="consultation", name="Consultation", questions=(), commercial_path="quote", quote_price="not-a-price"
        )


def test_direct_step_path_sets_next_step_message():
    update = _update(
        services=(
            SettingsServiceInput(
                id="consultation",
                name="Consultation",
                questions=(),
                commercial_path="direct_step",
                next_step_message="Head to our store to place your order.",
            ),
        ),
    )
    config = BusinessDNASettingsService._apply(_base_config(), update)
    service = config["services"][0]
    assert service["fulfillment_type"] == "direct_sale"
    assert service["booking_allowed"] is False
    assert service["direct_next_step_message"] == "Head to our store to place your order."
    assert "quoting" not in service


def test_direct_step_path_requires_message():
    with pytest.raises(ValueError, match="requires a message"):
        SettingsServiceInput(id="consultation", name="Consultation", questions=(), commercial_path="direct_step")


def test_switching_away_from_quote_clears_stale_quoting():
    config = _base_config()
    config["services"][0]["fulfillment_type"] = "quote_required"
    config["services"][0]["quoting"] = {
        "pricing_type": "fixed",
        "automatic_quote_allowed": True,
        "required_pricing_inputs": [],
        "pricing_input_questions": {},
        "fixed_price": "150",
    }
    update = _update(
        services=(
            SettingsServiceInput(id="consultation", name="Consultation", questions=(), commercial_path="human_review"),
        ),
    )
    result = BusinessDNASettingsService._apply(config, update)
    assert "quoting" not in result["services"][0]


def test_unrecognized_commercial_path_rejected():
    with pytest.raises(ValueError, match="not recognized"):
        SettingsServiceInput(id="consultation", name="Consultation", questions=(), commercial_path="carrier_pigeon")


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


def test_remote_business_with_no_rules_gets_auto_qualify_rule_injected():
    # Regression test: without this, QualificationService._qualification_rule_outcome
    # falls through to default_outcome ("needs_human") for every lead of a
    # remote business, since there's no service-area rule to gate "qualified"
    # on the way local/zip-enforced businesses do.
    config = _base_config()
    config["qualification"] = {"enforce_service_area": False}
    result = BusinessDNASettingsService._apply(config, _update(service_zip_codes=()))
    assert result["qualification"]["rules"] == [
        {"field": "service_id", "operator": "exists", "value": True, "outcome": "qualified"}
    ]


def test_remote_business_with_existing_rules_is_not_overwritten():
    config = _base_config()
    config["qualification"] = {
        "enforce_service_area": False,
        "rules": [{"field": "notes", "operator": "equals", "value": "x", "outcome": "lost"}],
    }
    result = BusinessDNASettingsService._apply(config, _update(service_zip_codes=()))
    assert result["qualification"]["rules"] == [
        {"field": "notes", "operator": "equals", "value": "x", "outcome": "lost"}
    ]


def test_local_business_rules_are_left_alone():
    config = _base_config()
    config["qualification"] = {"enforce_service_area": False}
    result = BusinessDNASettingsService._apply(config, _update(service_zip_codes=("94103",)))
    assert "rules" not in result["qualification"]
