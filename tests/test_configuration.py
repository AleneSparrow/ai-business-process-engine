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


def test_commercial_schema_requires_explicit_authority_and_currency() -> None:
    schema = load_json("business_dna.schema.json")
    validator = Draft202012Validator(schema)
    config = load_json("business_dna.example.json")

    no_path = deepcopy(config)
    del no_path["services"][0]["fulfillment_type"]
    with pytest.raises(ValidationError):
        validator.validate(no_path)

    no_quote_authority = deepcopy(config)
    del no_quote_authority["services"][1]["quoting"]["automatic_quote_allowed"]
    with pytest.raises(ValidationError):
        validator.validate(no_quote_authority)

    bad_payment_currency = deepcopy(config)
    bad_payment_currency["payment"]["currency"] = "usd"
    with pytest.raises(ValidationError):
        validator.validate(bad_payment_currency)


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
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings.from_environment()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://example.invalid/test")
    with pytest.raises(RuntimeError, match="AI_PROVIDER"):
        Settings.from_environment()
    monkeypatch.setenv("AI_PROVIDER", "deterministic")
    assert Settings.from_environment().database_url.endswith("/test")


def test_openai_settings_require_credentials_without_exposing_key_in_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://example.invalid/test")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        Settings.from_environment()

    marker = "sensitive-test-key-marker"
    monkeypatch.setenv("OPENAI_API_KEY", marker)
    settings = Settings.from_environment()
    assert settings.ai_provider == "openai"
    assert marker not in repr(settings)


def test_production_rejects_wildcard_cors_and_parses_public_chat_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://example.invalid/test")
    monkeypatch.setenv("AI_PROVIDER", "deterministic")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="wildcard CORS"):
        Settings.from_environment()

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, https://site.example")
    monkeypatch.setenv("PUBLIC_CHAT_RATE_LIMIT_REQUESTS", "7")
    settings = Settings.from_environment()
    assert settings.cors_allowed_origins == (
        "http://localhost:3000",
        "https://site.example",
    )
    assert settings.public_chat_rate_limit_requests == 7


def test_development_seed_refuses_production_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from examples.seed_example_business import main

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://example.invalid/production")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AI_PROVIDER", "deterministic")
    with pytest.raises(RuntimeError, match="development seed requires"):
        main()
