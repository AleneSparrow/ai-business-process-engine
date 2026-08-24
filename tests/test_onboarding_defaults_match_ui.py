"""The signup wizard's defaults must agree with the engine's defaults.

Found live on 2026-08-24: `escalate_on_high_urgency` was flipped to False in
OnboardingInput and in the API schema (variant C, see
claude/unit-economics-and-urgency-default.md), but web/app's wizard still
started at `true` and sent it on every signup. Two of the three places were
updated, so the change reached exactly zero real businesses -- a high-urgency
lead kept stopping the cycle on arrival, which is the behaviour the decision
existed to remove.

Nothing connected the React form to the dataclass, so no existing test could
notice. This one parses the wizard's initial state and compares it against the
dataclass field defaults, asserting they AGREE rather than hardcoding either
value -- so a future deliberate change to the default stays valid as long as
both sides move together.
"""

import ast
from dataclasses import fields
from pathlib import Path
import re

from src.domain.business_dna_builder import OnboardingInput


ROOT = Path(__file__).resolve().parents[1]
WIZARD = ROOT / "web" / "app" / "src" / "pages" / "Onboarding.tsx"

# Wizard state key -> OnboardingInput field name.
ESCALATION_FIELDS = {
    "highUrgency": "escalate_on_high_urgency",
    "emergency": "escalate_on_emergency",
}


def _dataclass_defaults() -> dict[str, bool]:
    return {
        field.name: field.default
        for field in fields(OnboardingInput)
        if field.name in ESCALATION_FIELDS.values()
    }


def _wizard_defaults() -> dict[str, bool]:
    """Read the initial escalation state out of the wizard source.

    Deliberately parses the file rather than importing it: there is no JS
    runtime in the test environment, and the point is to catch the source
    files drifting apart, which a parse does exactly as well.
    """
    source = WIZARD.read_text(encoding="utf-8")
    match = re.search(
        r"useState<EscalationState>\(\s*\{(?P<body>[^}]*)\}\s*\)",
        source,
    )
    assert match is not None, (
        "could not find the EscalationState useState initialiser in "
        f"{WIZARD.relative_to(ROOT)} -- if the wizard was restructured, update "
        "this test rather than deleting it; the drift it guards against is real"
    )
    found: dict[str, bool] = {}
    for key, value in re.findall(r"(\w+)\s*:\s*(true|false)", match.group("body")):
        if key in ESCALATION_FIELDS:
            found[ESCALATION_FIELDS[key]] = value == "true"
    return found


def test_wizard_ships_every_escalation_default_the_engine_defines() -> None:
    """A field the engine defaults must not be silently absent from the wizard."""
    assert set(_wizard_defaults()) == set(_dataclass_defaults()), (
        "the wizard and OnboardingInput disagree about which escalation "
        "switches exist"
    )


def test_wizard_escalation_defaults_match_the_engine() -> None:
    """The exact regression: backend default changed, wizard kept sending the old one."""
    wizard = _wizard_defaults()
    engine = _dataclass_defaults()
    mismatched = {
        name: (wizard[name], engine[name])
        for name in engine
        if wizard[name] != engine[name]
    }
    assert not mismatched, (
        "signup wizard and engine defaults disagree "
        f"(field: wizard sends / engine expects): {mismatched}. "
        "A default changed on one side only, so real signups keep the old "
        "behaviour while the tests pass."
    )


def test_api_schema_default_matches_the_engine() -> None:
    """The third copy of the same default -- keep all three in step."""
    from src.api.schemas import OnboardingRequest

    engine = _dataclass_defaults()
    schema_fields = OnboardingRequest.model_fields
    mismatched = {
        name: (schema_fields[name].default, engine[name])
        for name in engine
        if name in schema_fields and schema_fields[name].default != engine[name]
    }
    assert not mismatched, (
        f"API schema and engine defaults disagree (schema / engine): {mismatched}"
    )


def test_wizard_actually_sends_the_state_it_initialises() -> None:
    """Guards the other half: a correct default is useless if it isn't sent.

    The wizard could hold the right initial value and still post a literal, or
    post nothing at all, in which case the schema default silently applies and
    the checkbox becomes decorative.
    """
    source = WIZARD.read_text(encoding="utf-8")
    for wizard_key, field_name in ESCALATION_FIELDS.items():
        assert re.search(rf"{field_name}\s*:\s*escalation\.{wizard_key}\b", source), (
            f"{field_name} is not posted from the wizard's own escalation state "
            "-- the checkbox does not reach the backend"
        )
