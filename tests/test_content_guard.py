from pathlib import Path

import pytest

from scripts.content_guard import (
    lint_body,
    lint_posts,
    load_rules,
    parse_posts,
)

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "docs/marketing/founder-presence/06-post-queue.md"
RULES = ROOT / "docs/marketing/founder-presence/guardrails.yaml"


@pytest.fixture(scope="module")
def rules() -> dict:
    return load_rules(RULES)


def test_queue_parses_linkedin_and_x_posts() -> None:
    posts = parse_posts(QUEUE.read_text(encoding="utf-8"))
    ids = {post.post_id for post in posts}
    assert "LI-001" in ids
    assert "X-001" in ids
    assert len(posts) >= 24
    assert all(post.body.strip() for post in posts)


def test_live_queue_passes_guardrails(rules: dict) -> None:
    posts = parse_posts(QUEUE.read_text(encoding="utf-8"))
    assert lint_posts(posts, rules) == []


def test_cold_lead_is_rejected(rules: dict) -> None:
    hits = lint_body("LI-TEST", "We help you convert a cold lead overnight.", rules)
    assert any(hit.detail == "cold lead" for hit in hits)


def test_negated_generate_demand_is_allowed(rules: dict) -> None:
    text = "Flywheel does not generate demand. It closes the cycle you already paid for."
    assert lint_body("LI-TEST", text, rules) == []


def test_positive_generate_demand_is_rejected(rules: dict) -> None:
    hits = lint_body("LI-TEST", "Flywheel will generate demand for your firm.", rules)
    assert any(hit.rule == "positive_claim" for hit in hits)


def test_intake_self_name_is_rejected(rules: dict) -> None:
    hits = lint_body("LI-TEST", "Flywheel is an intake assistant for busy owners.", rules)
    assert any(hit.detail == "intake assistant" for hit in hits)


def test_missing_product_name_on_linkedin(rules: dict) -> None:
    hits = lint_body("LI-999", "I shipped a state machine today.", rules)
    assert any(hit.rule == "missing_product_name" for hit in hits)
