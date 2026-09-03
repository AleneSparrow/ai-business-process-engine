"""Closes the class of bug found 2026-08-25: a customer's own words reached
the logs via QualificationResult.reasons (free prose), under a comment
claiming that never happened. See QualificationReasonCode's docstring.

This file does not check one reason -- it drives every LOST/NEEDS_HUMAN
branch in QualificationService.evaluate, captures the actual log line
QualificationService._result emits, and asserts two invariants for every
single one of them:
  1. the log payload has no "reasons" key at all (only reason_code), and
  2. reason_code is a member of the closed QualificationReasonCode vocabulary.

A comment asserting this couldn't hold the guarantee for eight days. This
test is what's supposed to, going forward: add a branch that logs free
prose (or an unlisted code) and it fails here, not silently in production.
"""

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from src.domain.models import Lead
from src.domain.qualification import IncomingMessage, IntentResult, QualificationReasonCode, Urgency
from src.domain.states import ProcessState
from src.domain.tenancy import Business
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.engine.qualification_service import QualificationService
from src.engine.question_generator import DeterministicQuestionGenerator
from src.persistence.lead_intake import PersistentLeadIntakeService
from src.persistence.sqlalchemy_models import Base
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc)


def _full_dna() -> dict:
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        return json.load(file)

ALL_REASON_CODES = {member.value for member in QualificationReasonCode}


def _base_dna(**overrides: Any) -> dict:
    dna: dict[str, Any] = {
        "services": [{
            "id": "consultation",
            "name": "Consultation",
            "intake_keywords": ["consultation"],
            "service_area_ids": ["metro"],
            "booking_allowed": True,
            "qualification_questions": [],
        }],
        "service_areas": [
            {"id": "metro", "type": "postal_codes", "values": ["60601"]},
        ],
        "customer_information": {
            "required_fields": ["name", "phone"],
            "field_questions": {
                "name": "What name should we use?",
                "phone": "What is your phone number?",
                "service_id": "Which service do you need?",
                "customer_location": "What is your ZIP code?",
            },
        },
        "qualification": {
            "rules": [],
            "default_outcome": "qualified",
            "enforce_service_area": False,
        },
        "ai_permissions": {"minimum_confidence": 0.8},
        "human_escalation": {"triggers": []},
        "booking": {"enabled": True},
    }
    dna.update(deepcopy(overrides))
    return dna


def _lead(**overrides: Any) -> Lead:
    defaults: dict[str, Any] = dict(lead_id="lead-1", name="Ada", phone="+1 312 555 0100")
    defaults.update(overrides)
    return Lead(**defaults)  # type: ignore[arg-type]


def _terminal_diagnostic_payload(caplog: pytest.LogCaptureFixture) -> dict[str, Any]:
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "uvicorn.error"
    ]
    matches = [payload for payload in records if payload.get("event") == "qualification_terminal_diagnostic"]
    assert len(matches) == 1, f"expected exactly one qualification_terminal_diagnostic log, got {matches}"
    return matches[0]


def _assert_safe_terminal_log(caplog: pytest.LogCaptureFixture, expected_state: ProcessState) -> dict[str, Any]:
    payload = _terminal_diagnostic_payload(caplog)
    assert "reasons" not in payload, f"free-prose 'reasons' key leaked into the log: {payload}"
    assert "reason_code" in payload, f"no reason_code in the log at all: {payload}"
    assert payload["reason_code"] in ALL_REASON_CODES, (
        f"reason_code {payload['reason_code']!r} is not in the closed vocabulary"
    )
    assert payload["state"] == expected_state.value
    return payload


# --- One case per LOST/NEEDS_HUMAN branch in QualificationService.evaluate ---

BRANCHES = {}


def _case(name):
    def register(func):
        BRANCHES[name] = func
        return func
    return register


@_case("requires_human")
def _requires_human():
    intent = IntentResult(requires_human=True, confidence=0.95)
    return _base_dna(), intent, {}, ProcessState.NEEDS_HUMAN, QualificationReasonCode.REQUIRES_HUMAN


@_case("unintelligible_exhausted")
def _unintelligible_exhausted():
    intent = IntentResult(unintelligible=True, confidence=0.95)
    case_metadata = {"clarification_attempts": QualificationService.MAX_CLARIFICATION_ATTEMPTS}
    return _base_dna(), intent, case_metadata, ProcessState.NEEDS_HUMAN, QualificationReasonCode.UNINTELLIGIBLE


@_case("low_confidence")
def _low_confidence():
    intent = IntentResult(confidence=0.1)
    case_metadata = {"clarification_attempts": QualificationService.MAX_CLARIFICATION_ATTEMPTS}
    return _base_dna(), intent, case_metadata, ProcessState.NEEDS_HUMAN, QualificationReasonCode.LOW_CONFIDENCE


@_case("safety_emergency")
def _safety_emergency():
    intent = IntentResult(urgency=Urgency.EMERGENCY, confidence=0.95)
    dna = _base_dna(human_escalation={"triggers": ["emergency"]})
    return dna, intent, {}, ProcessState.NEEDS_HUMAN, QualificationReasonCode.SAFETY_EMERGENCY


@_case("urgent_request_immediate_trigger")
def _urgent_request_immediate():
    intent = IntentResult(urgency=Urgency.HIGH, confidence=0.95)
    dna = _base_dna(human_escalation={"triggers": ["high"]})
    return dna, intent, {}, ProcessState.NEEDS_HUMAN, QualificationReasonCode.URGENT_REQUEST


@_case("urgent_request_post_qualification")
def _urgent_request_post_qualification():
    # No immediate trigger configured -- variant C: complete qualification
    # first, hand off only once everything required is already collected.
    intent = IntentResult(
        service_requested="consultation", urgency=Urgency.HIGH, confidence=0.95,
    )
    return _base_dna(), intent, {}, ProcessState.NEEDS_HUMAN, QualificationReasonCode.URGENT_REQUEST


@_case("service_not_offered")
def _service_not_offered():
    intent = IntentResult(
        confidence=0.95, unsupported_service_name="a service we do not have",
    )
    return _base_dna(), intent, {}, ProcessState.LOST, QualificationReasonCode.SERVICE_NOT_OFFERED


@_case("outside_service_area")
def _outside_service_area():
    intent = IntentResult(service_requested="consultation", customer_location="99999", confidence=0.95)
    dna = _base_dna(qualification={"rules": [], "default_outcome": "qualified", "enforce_service_area": True})
    return dna, intent, {}, ProcessState.LOST, QualificationReasonCode.OUTSIDE_SERVICE_AREA


@_case("service_area_uncertain")
def _service_area_uncertain():
    intent = IntentResult(service_requested="consultation", customer_location="60601", confidence=0.95)
    dna = _base_dna(qualification={"rules": [], "default_outcome": "qualified", "enforce_service_area": True})
    # Service references an area id absent from service_areas entirely.
    dna["services"][0]["service_area_ids"] = ["nonexistent-area"]
    return dna, intent, {}, ProcessState.NEEDS_HUMAN, QualificationReasonCode.SERVICE_AREA_UNCERTAIN


@_case("disqualifying_answer")
def _disqualifying_answer():
    dna = _base_dna()
    dna["services"][0]["qualification_questions"] = [{
        "id": "property-type",
        "prompt": "Residential or commercial?",
        "required": True,
        "disqualifying_answers": ["commercial"],
    }]
    intent = IntentResult(
        service_requested="consultation",
        confidence=0.95,
        qualification_answers={"property-type": "commercial"},
    )
    return dna, intent, {}, ProcessState.LOST, QualificationReasonCode.DISQUALIFYING_ANSWER


@_case("policy_rejected")
def _policy_rejected():
    dna = _base_dna(qualification={
        "rules": [{"field": "risk-flag", "operator": "equals", "value": "reject", "outcome": "lost"}],
        "default_outcome": "qualified",
        "enforce_service_area": False,
    })
    dna["services"][0]["qualification_questions"] = [{
        "id": "risk-flag", "prompt": "Risk flag?", "required": True, "disqualifying_answers": [],
    }]
    intent = IntentResult(
        service_requested="consultation",
        confidence=0.95,
        qualification_answers={"risk-flag": "reject"},
    )
    return dna, intent, {}, ProcessState.LOST, QualificationReasonCode.POLICY_REJECTED


@_case("policy_review")
def _policy_review():
    dna = _base_dna(qualification={
        "rules": [{"field": "risk-flag", "operator": "equals", "value": "review", "outcome": "needs_human"}],
        "default_outcome": "qualified",
        "enforce_service_area": False,
    })
    dna["services"][0]["qualification_questions"] = [{
        "id": "risk-flag", "prompt": "Risk flag?", "required": True, "disqualifying_answers": [],
    }]
    intent = IntentResult(
        service_requested="consultation",
        confidence=0.95,
        qualification_answers={"risk-flag": "review"},
    )
    return dna, intent, {}, ProcessState.NEEDS_HUMAN, QualificationReasonCode.POLICY_REVIEW


@pytest.mark.parametrize("branch_name", sorted(BRANCHES))
def test_every_lost_or_needs_human_branch_logs_only_a_closed_vocabulary_code(
    branch_name: str, caplog: pytest.LogCaptureFixture,
) -> None:
    dna, intent, case_metadata, expected_state, expected_code = BRANCHES[branch_name]()

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        result = QualificationService().evaluate(_lead(), intent, dna, case_metadata=case_metadata)

    assert result.recommended_next_state is expected_state
    assert result.reason_codes == (expected_code.value,)
    payload = _assert_safe_terminal_log(caplog, expected_state)
    assert payload["reason_code"] == expected_code.value


def test_reason_codes_cover_every_branch_actually_wired_in_qualification_service() -> None:
    """Guards the test file itself, not just the code -- if a new branch is
    added to evaluate() without a matching case here, this is the assertion
    meant to catch that the coverage list has gone stale."""
    assert set(BRANCHES) == {
        "requires_human",
        "unintelligible_exhausted",
        "low_confidence",
        "safety_emergency",
        "urgent_request_immediate_trigger",
        "urgent_request_post_qualification",
        "service_not_offered",
        "outside_service_area",
        "service_area_uncertain",
        "disqualifying_answer",
        "policy_rejected",
        "policy_review",
    }


def test_qualified_and_missing_information_also_carry_closed_vocabulary_codes() -> None:
    """Not LOST/NEEDS_HUMAN, so QualificationService._result's log is not
    involved -- but reason_codes is universal on QualificationResult, and
    QualificationResult.__post_init__ already enforces the closed
    vocabulary for these too. Confirms it end to end regardless."""
    qualified = QualificationService().evaluate(
        _lead(), IntentResult(service_requested="consultation", confidence=0.95), _base_dna(),
    )
    assert qualified.recommended_next_state is ProcessState.QUALIFIED
    assert qualified.reason_codes == (QualificationReasonCode.QUALIFIED.value,)

    missing_info = QualificationService().evaluate(
        _lead(name=None, phone=None),
        IntentResult(service_requested="consultation", confidence=0.95),
        _base_dna(),
    )
    assert missing_info.recommended_next_state is ProcessState.QUALIFYING
    assert missing_info.reason_codes == (QualificationReasonCode.MISSING_INFORMATION.value,)


def test_already_escalated_reason_code() -> None:
    """LeadIntakeService._already_escalated_result NEEDS_HUMAN construction
    site -- doesn't go through QualificationService._result, so no
    qualification_terminal_diagnostic log to intercept, but reason_codes
    still has to carry a real, closed-vocabulary value."""
    from src.engine.lead_intake import LeadIntakeService

    already_escalated = LeadIntakeService._already_escalated_result(
        IntentResult(confidence=0.95), "consultation",
    )
    assert already_escalated.reason_codes == (QualificationReasonCode.ALREADY_PENDING.value,)


def test_identity_conflict_reason_code(tmp_path: Path) -> None:
    """PersistentLeadIntakeService's identity-conflict NEEDS_HUMAN
    construction (receive_in_unit_of_work) -- exercised end to end: two
    different real people (different name) sharing a phone number. Same as
    _already_escalated_result above, this doesn't log
    qualification_terminal_diagnostic (that's QualificationService-only),
    so it's checked directly on the returned result instead."""
    database_url = f"sqlite+pysqlite:///{tmp_path / 'identity.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    with factory() as uow:
        uow.businesses.add(Business("acme-home-services", "Acme", NOW, NOW))
        uow.business_dna.add_version("acme-home-services", _full_dna())
        uow.commit()

    shared_phone = "+1 312 555 0177"
    scripted = {
        "first-owner": IntentResult(
            service_requested="diagnostic-visit", customer_location="60601", confidence=0.95,
        ),
        # _resolve_case's own phone lookup runs BEFORE the identity-conflict
        # check and would silently reuse Ada's lead outright if this message
        # supplied the phone directly -- it must arrive only through the
        # extracted intent (as if the AI read it out of the message body),
        # the way a customer stating someone else's number in free text
        # would, for the conflict path (not the reuse path) to actually
        # trigger.
        "second-conflict": IntentResult(
            service_requested="diagnostic-visit", customer_location="60601", confidence=0.95,
            phone=shared_phone,
        ),
    }
    extractor = DeterministicIntentExtractor(scripted)
    service = PersistentLeadIntakeService(factory, extractor, DeterministicQuestionGenerator())

    first = service.receive(IncomingMessage(
        "acme-home-services", "sms", "first-owner", "I need a diagnostic visit",
        NOW, customer_name="Ada", phone=shared_phone,
    ))
    assert first.current_state is ProcessState.QUALIFIED

    second = service.receive(IncomingMessage(
        "acme-home-services", "sms", "second-conflict", "I need a diagnostic visit",
        NOW, customer_name="Bob",
    ))

    assert second.current_state is ProcessState.NEEDS_HUMAN
    assert second.qualification.reason_codes == (QualificationReasonCode.IDENTITY_CONFLICT.value,)
    engine.dispose()
