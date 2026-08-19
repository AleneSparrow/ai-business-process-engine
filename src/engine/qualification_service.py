"""Business-DNA-driven lead qualification."""

import json
import logging
import re
from typing import Any, Mapping

from src.domain.models import Lead
from src.domain.qualification import IntentResult, MissingInformationResult, QualificationResult
from src.domain.states import ProcessState

# TEMPORARY diagnostic logging (2026-08-17): not importing
# `src.api.observability.log_event` here -- src/api/app.py imports engine
# modules, so a dependency from src.engine back onto src.api risks a
# circular import if this module is ever the first one touched (e.g. a
# test importing it directly, before anything has imported src.api).
# Logging directly with the same "uvicorn.error" logger name keeps
# identical log output without that dependency direction.
_LOGGER = logging.getLogger("uvicorn.error")


def _log_event(level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: value for key, value in fields.items() if value is not None}}
    _LOGGER.log(level, json.dumps(payload, separators=(",", ":"), default=str))


class QualificationService:
    _POSTAL_CODE_LABEL = re.compile(
        r"^(?:zip(?:\s+code)?|postal\s+code|postcode)\s*(?:is\s+)?[:#-]?\s*",
        re.IGNORECASE,
    )

    def evaluate(
        self,
        lead: Lead,
        intent: IntentResult,
        business_dna: Mapping[str, Any],
    ) -> QualificationResult:
        threshold = float(business_dna["ai_permissions"]["minimum_confidence"])
        triggers = set(business_dna["human_escalation"]["triggers"])
        if intent.requires_human or intent.confidence < threshold:
            # TEMPORARY diagnostic logging (2026-08-17): distinguishes the
            # two ways this branch can fire -- confidence/threshold are
            # non-sensitive numeric config+model signals, never customer
            # content.
            _log_event(
                logging.INFO,
                "qualification_needs_human_diagnostic",
                reason="requires_human" if intent.requires_human else "below_confidence_threshold",
                confidence=intent.confidence,
                threshold=threshold,
            )
            return self._result(
                ProcessState.NEEDS_HUMAN,
                ("Intent confidence is below policy or extraction requested review",),
                intent,
            )
        if intent.urgency.value in triggers:
            return self._result(
                ProcessState.NEEDS_HUMAN,
                (f"Configured escalation trigger matched urgency: {intent.urgency.value}",),
                intent,
            )

        service = self._find_service(intent.service_requested, business_dna["services"])
        if intent.service_requested and service is None:
            return self._result(
                ProcessState.LOST,
                (f"Requested service is not offered: {intent.service_requested}",),
                intent,
            )

        context = self._context(lead, intent, service)
        required_fields = tuple(business_dna["customer_information"]["required_fields"])
        missing_fields = tuple(field for field in required_fields if not self._has_value(context.get(field)))

        if service is None and "service_id" not in missing_fields:
            missing_fields = (*missing_fields, "service_id")

        area_status, area_id = self._service_area_status(intent, service, business_dna)
        location_fields = {"customer_location", "service_address", "postal_code"}
        if area_status == "missing" and not location_fields.intersection(missing_fields):
            missing_fields = (*missing_fields, "customer_location")
        elif area_status == "outside":
            return self._result(ProcessState.LOST, ("Customer is outside the configured service area",), intent, service)
        elif area_status == "unknown":
            return self._result(
                ProcessState.NEEDS_HUMAN,
                ("Service area cannot be evaluated deterministically",),
                intent,
                service,
            )

        context["service_area_id"] = area_id
        unanswered, disqualified = self._qualification_questions(service, context)
        if disqualified:
            return self._result(ProcessState.LOST, tuple(disqualified), intent, service)

        missing = MissingInformationResult(tuple(dict.fromkeys(missing_fields)), tuple(unanswered))
        if not missing.complete:
            return QualificationResult(
                qualified=False,
                reasons=("Additional customer information is required",),
                missing_fields=missing.missing_fields,
                unanswered_questions=missing.unanswered_questions,
                confidence=intent.confidence,
                recommended_next_state=ProcessState.QUALIFYING,
                requires_human=False,
                booking_allowed=False,
                service_id=self._service_id(service),
                # Passed through untouched -- which (if any) configured
                # objection_responses entry answers it is decided later, in
                # response generation, never here.
                objection_phrase=intent.objection_phrase,
            )

        rule_outcome = self._qualification_rule_outcome(context, business_dna["qualification"])
        if rule_outcome in {"lost", "disqualified"}:
            return self._result(ProcessState.LOST, ("A configured qualification rule rejected the lead",), intent, service)
        if rule_outcome in {"needs_human", "human"}:
            return self._result(
                ProcessState.NEEDS_HUMAN,
                ("Configured qualification policy requires human review",),
                intent,
                service,
            )

        booking_allowed = bool(
            service
            and service.get("booking_allowed", True)
            and business_dna["booking"].get("enabled", True)
        )
        return QualificationResult(
            qualified=True,
            reasons=("All mandatory qualification requirements are satisfied",),
            missing_fields=(),
            unanswered_questions=(),
            confidence=intent.confidence,
            recommended_next_state=ProcessState.QUALIFIED,
            requires_human=False,
            booking_allowed=booking_allowed,
            service_id=self._service_id(service),
        )

    @staticmethod
    def _find_service(requested: str | None, services: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        if requested is None:
            return None
        normalized = requested.strip().casefold()
        matches = []
        for service in services:
            terms = (service["id"], service["name"], *service.get("intake_keywords", []))
            if normalized in {str(term).strip().casefold() for term in terms}:
                matches.append(service)
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _context(
        lead: Lead,
        intent: IntentResult,
        service: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        context = dict(lead.attributes)
        context.update({
            "name": lead.name,
            "phone": lead.phone,
            "email": lead.email,
            "service_id": service.get("id") if service else None,
            "service_requested": intent.service_requested,
            "customer_location": intent.customer_location or context.get("customer_location"),
            "service_address": intent.customer_location or context.get("customer_location"),
            "postal_code": intent.customer_location or context.get("customer_location"),
            "preferred_time": intent.preferred_time or context.get("preferred_time"),
            "notes": intent.notes or context.get("notes"),
        })
        answers = dict(context.get("qualification_answers", {}))
        answers.update(intent.qualification_answers)
        context["qualification_answers"] = answers
        context.update(answers)
        return context

    @staticmethod
    def _service_area_status(
        intent: IntentResult,
        service: Mapping[str, Any] | None,
        business_dna: Mapping[str, Any],
    ) -> tuple[str, str | None]:
        if not business_dna["qualification"].get("enforce_service_area", False) or service is None:
            return "inside", None
        location = intent.customer_location
        if not location:
            return "missing", None
        normalized = location.strip().casefold()
        configured = {area["id"]: area for area in business_dna["service_areas"]}
        unknown_type = False
        for area_id in service.get("service_area_ids", []):
            area = configured.get(area_id)
            if area is None:
                return "unknown", None
            if area["type"] == "remote":
                return "inside", area_id
            if area["type"] == "postal_codes":
                configured_values = {
                    str(value).strip().casefold() for value in area["values"]
                }
                if QualificationService._postal_code_value(normalized) in configured_values:
                    return "inside", area_id
            elif area["type"] in {"cities", "regions"}:
                if normalized in {
                    str(value).strip().casefold() for value in area["values"]
                }:
                    return "inside", area_id
            else:
                unknown_type = True
        return ("unknown", None) if unknown_type else ("outside", None)

    @staticmethod
    def _postal_code_value(location: str) -> str:
        """Remove only explicit postal labels; eligibility still uses exact configured values."""

        without_label = QualificationService._POSTAL_CODE_LABEL.sub("", location, count=1)
        return without_label.strip(" \t.,;")

    @staticmethod
    def _qualification_questions(
        service: Mapping[str, Any] | None,
        context: Mapping[str, Any],
    ) -> tuple[list[str], list[str]]:
        unanswered: list[str] = []
        disqualified: list[str] = []
        if service is None:
            return unanswered, disqualified
        answers = context.get("qualification_answers", {})
        for question in service.get("qualification_questions", []):
            question_id = question["id"]
            answer = answers.get(question_id) if isinstance(answers, Mapping) else None
            if question.get("required", True) and not QualificationService._has_value(answer):
                unanswered.append(question["prompt"])
                continue
            rejected = {str(value).casefold() for value in question.get("disqualifying_answers", [])}
            if answer is not None and str(answer).casefold() in rejected:
                disqualified.append(f"Qualification answer rejected by policy: {question_id}")
        return unanswered, disqualified

    @staticmethod
    def _qualification_rule_outcome(context: Mapping[str, Any], qualification: Mapping[str, Any]) -> str:
        for rule in qualification.get("rules", []):
            actual = context.get(rule["field"])
            expected = rule.get("value")
            operator = rule["operator"]
            if operator == "equals":
                matched = actual == expected
            elif operator == "not_equals":
                matched = actual != expected
            elif operator == "in":
                matched = actual in expected if isinstance(expected, list) else False
            elif operator == "not_in":
                matched = actual not in expected if isinstance(expected, list) else False
            elif operator in {"greater_than", "less_than"}:
                try:
                    matched = actual > expected if operator == "greater_than" else actual < expected
                except TypeError:
                    matched = False
            else:
                matched = QualificationService._has_value(actual)
            if matched:
                return str(rule["outcome"]).casefold()
        return str(qualification.get("default_outcome", "qualified")).casefold()

    @staticmethod
    def _has_value(value: Any) -> bool:
        return value is not None and (not isinstance(value, str) or bool(value.strip()))

    @staticmethod
    def _service_id(service: Mapping[str, Any] | None) -> str | None:
        return str(service["id"]) if service else None

    @staticmethod
    def _result(
        state: ProcessState,
        reasons: tuple[str, ...],
        intent: IntentResult,
        service: Mapping[str, Any] | None = None,
    ) -> QualificationResult:
        if state in (ProcessState.NEEDS_HUMAN, ProcessState.LOST):
            # TEMPORARY diagnostic logging (2026-08-17): reasons are this
            # file's own fixed strings, never customer content.
            _log_event(
                logging.INFO,
                "qualification_terminal_diagnostic",
                state=state.value,
                reasons=reasons,
                service_id=QualificationService._service_id(service),
            )
        return QualificationResult(
            qualified=state is ProcessState.QUALIFIED,
            reasons=reasons,
            missing_fields=(),
            unanswered_questions=(),
            confidence=intent.confidence,
            recommended_next_state=state,
            requires_human=state is ProcessState.NEEDS_HUMAN,
            booking_allowed=bool(service and service.get("booking_allowed", True) and state is ProcessState.QUALIFIED),
            service_id=QualificationService._service_id(service),
        )
