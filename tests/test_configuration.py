import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError

from src.config import Settings
from src.domain.state_machine import TRANSITIONS
from src.domain.states import ProcessState


ROOT = Path(__file__).parents[1]


def load_json(name: str) -> dict:
    with (ROOT / "config" / name).open(encoding="utf-8") as file:
        return json.load(file)


def test_business_dna_example_validates_against_schema() -> None:
    schema = load_json("business_dna.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(load_json("business_dna.example.json"))


def test_schema_rejects_secret_like_integration_keys_and_bad_times() -> None:
    schema = load_json("business_dna.schema.json")
    validator = Draft202012Validator(schema)
    config = load_json("business_dna.example.json")

    with_secret = deepcopy(config)
    with_secret["integrations"]["api_key"] = {"provider": "x", "connection_reference": "plaintext"}
    with pytest.raises(ValidationError):
        validator.validate(with_secret)

    bad_time = deepcopy(config)
    bad_time["communication"]["quiet_hours"]["starts"] = "25:99"
    with pytest.raises(ValidationError):
        validator.validate(bad_time)


def test_priced_service_models_require_an_amount() -> None:
    schema = load_json("business_dna.schema.json")
    config = load_json("business_dna.example.json")
    del config["services"][0]["pricing"]["amount"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(config)


def test_yaml_workflow_exactly_matches_python_state_machine() -> None:
    with (ROOT / "workflows" / "lead_to_cash.yaml").open(encoding="utf-8") as file:
        workflow = yaml.safe_load(file)

    yaml_transitions = {
        ProcessState(state): frozenset(ProcessState(target) for target in targets)
        for state, targets in workflow["states"].items()
    }
    assert workflow["initial_state"] == ProcessState.NEW_LEAD.value
    assert yaml_transitions == TRANSITIONS


def test_database_settings_require_environment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings.from_environment()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://example.invalid/test")
    assert Settings.from_environment().database_url.endswith("/test")


def test_development_seed_refuses_production_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from examples.seed_example_business import main

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://example.invalid/production")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="development seed requires"):
        main()
