"""Business-DNA-driven lead qualification."""

import json
import logging
import re
from typing import Any, Mapping, MutableMapping

from src.domain.models import Lead
from src.domain.qualification import (
    IntentResult,
    MissingInformationResult,
    QualificationReasonCode,
    QualificationResult,
    Urgency,
)
from src.domain.states import ProcessState

# Permanent architectural note, not a temporary measure: not importing
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


# The engine distinguishes four different LOST reasons, but until 2026-08-25
# every one of them produced the same customer-facing sentence
# (qualification.lost_message). A lead ten miles outside the service area heard
# the identical wording as someone asking for a service the business does not
# offer, and left without learning that a different address was all it took --
# a straight loss at the edge of the cycle, worst in exactly the field-service
# verticals (plumbing, roofing, HVAC) where the service area IS the filter.
#
# This constant exists so LeadIntakeService can recognise THIS reason without
# matching on prose. Reasons are this module's own fixed strings and never
# contain customer content, so comparing against them is safe -- but they are
# still prose, so there is exactly one place that spells this one out.
SERVICE_NOT_OFFERED_REASON = "Requested service is not offered"
OUT_OF_SERVICE_AREA_REASON = "Customer is outside the configured service area"


class QualificationService:
    _POSTAL_CODE_LABEL = re.compile(
        r"^(?:zip(?:\s+code)?|postal\s+code|postcode)\s*(?:is\s+)?[:#-]?\s*",
        re.IGNORECASE,
    )

    # Bounded per case, mirroring LeadIntakeService.MAX_REASSURANCE_ATTEMPTS --
    # see universal-sales-cycle-model.md section 6 ("Ограничение
    # настойчивости"). A message we cannot act on yet -- one the AI could not
    # interpret at all (intent.unintelligible) OR one it read with confidence
    # below the business's threshold -- stays in the automated clarification
    # loop instead of escalating immediately, but only up to this many
    # attempts per case; once exhausted it escalates like any other
    # unresolved case. Without this cap a customer who never sends an
    # interpretable message would loop with the bot forever and never reach
    # a human.
    #
    # Low confidence joined this loop on 2026-09-01. Before that it escalated
    # on the spot, without asking anything: a first message of "Hi! what do
    # you want?" went straight to NEEDS_HUMAN, and "Low confidence in the
    # request" was the single largest escalation reason on production (36 of
    # 77). That is intake, not "from enquiry to deal" -- and CLAUDE.md
    # already required the opposite ("переспрос на непонятном сообщении
    # вместо сброса на человека"); the requirement was simply only
    # implemented for the unintelligible flag, which prompts.py deliberately
    # keeps distinct from low confidence ("do not set unintelligible merely
    # because confidence is low").
    MAX_CLARIFICATION_ATTEMPTS = 3

    def evaluate(
        self,
        lead: Lead,
        intent: IntentResult,
        business_dna: Mapping[str, Any],
        case_metadata: MutableMapping[str, Any] | None = None,
    ) -> QualificationResult:
        threshold = float(business_dna["ai_permissions"]["minimum_confidence"])
        triggers = set(business_dna["human_escalation"]["triggers"])
        if intent.requires_human:
            # Load-bearing, keep. Distinguishes the two ways this branch
            # can fire -- confidence/threshold are numeric config+model
            # signals, never customer content.
            #
            # Concretely earned its keep on 2026-08-24: this exact line
            # (reason="requires_human", confidence 0.93, threshold 0.8) is
            # what identified why a routine high-urgency request was still
            # escalating on message one after the variant C change.
            # Removing it as "expired" would have cost that diagnosis.
            _log_event(
                logging.INFO,
                "qualification_needs_human_diagnostic",
                reason="requires_human",
                confidence=intent.confidence,
                threshold=threshold,
            )
            return self._result(
                ProcessState.NEEDS_HUMAN,
                ("Intent confidence is below policy or extraction requested review",),
                QualificationReasonCode.REQUIRES_HUMAN,
                intent,
            )
        low_confidence = not intent.unintelligible and intent.confidence < threshold
        if intent.unintelligible or low_confidence:
            attempts = self._clarification_attempts(case_metadata)
            if attempts >= self.MAX_CLARIFICATION_ATTEMPTS:
                _log_event(
                    logging.INFO,
                    "qualification_needs_human_diagnostic",
                    reason=(
                        "below_confidence_threshold_attempts_exhausted" if low_confidence
                        else "unintelligible_attempts_exhausted"
                    ),
                    confidence=intent.confidence,
                    threshold=threshold,
                    attempts=attempts,
                )
                return self._result(
                    ProcessState.NEEDS_HUMAN,
                    (
                        ("Intent confidence is below policy or extraction requested review",)
                        if low_confidence
                        else ("Customer message could not be interpreted after repeated clarification attempts",)
                    ),
                    (
                        QualificationReasonCode.LOW_CONFIDENCE if low_confidence
                        else QualificationReasonCode.UNINTELLIGIBLE
                    ),
                    intent,
                )
            self._record_clarification_attempt(case_metadata, attempts)
            # Treated as "no new information this turn" and falls through to
            # the ordinary missing-fields flow below -- same as any other
            # message that doesn't add a fact, never a special-cased
            # response. For an unintelligible message this also means
            # confidence.threshold is deliberately NOT checked for this turn:
            # its confidence score isn't a meaningful signal either way.
            #
            # A low-confidence turn falls through the SAME way, but may not
            # finish the case on that turn -- see the guard after the
            # missing-information block. Asking one more question on a shaky
            # reading is cheap; booking on one is not.
        if intent.urgency.value in triggers:
            return self._result(
                ProcessState.NEEDS_HUMAN,
                (f"Configured escalation trigger matched urgency: {intent.urgency.value}",),
                (
                    QualificationReasonCode.SAFETY_EMERGENCY
                    if intent.urgency is Urgency.EMERGENCY
                    else QualificationReasonCode.URGENT_REQUEST
                ),
                intent,
            )

        service = self._find_service(intent.service_requested, business_dna["services"])
        # The customer's own wording for the thing we don't offer is NOT
        # interpolated here any more. This reason string reaches the terminal
        # diagnostic log below, and service_requested used to be able to hold
        # arbitrary customer prose (see IntentResult.unsupported_service_name).
        # The phrase is preserved for staff on the case metadata instead, which
        # is stored rather than logged.
        if intent.unsupported_service_name is not None or (
            intent.service_requested and service is None
        ):
            return self._result(
                ProcessState.LOST,
                (SERVICE_NOT_OFFERED_REASON,),
                QualificationReasonCode.SERVICE_NOT_OFFERED,
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
            return self._result(
                ProcessState.LOST,
                (OUT_OF_SERVICE_AREA_REASON,),
                QualificationReasonCode.OUTSIDE_SERVICE_AREA,
                intent,
                service,
            )
        elif area_status == "unknown":
            return self._result(
                ProcessState.NEEDS_HUMAN,
                ("Service area cannot be evaluated deterministically",),
                QualificationReasonCode.SERVICE_AREA_UNCERTAIN,
                intent,
                service,
            )

        context["service_area_id"] = area_id
        unanswered, disqualified = self._qualification_questions(service, context)
        if disqualified:
            return self._result(
                ProcessState.LOST,
                tuple(disqualified),
                QualificationReasonCode.DISQUALIFYING_ANSWER,
                intent,
                service,
            )

        missing = MissingInformationResult(tuple(dict.fromkeys(missing_fields)), tuple(unanswered))
        if not missing.complete:
            return QualificationResult(
                qualified=False,
                reasons=("Additional customer information is required",),
                reason_codes=(QualificationReasonCode.MISSING_INFORMATION,),
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

        if low_confidence:
            # Everything required is present, but this turn's reading was
            # below the business's confidence threshold, so the service or
            # answers it produced may be wrong. Falling through to a booking
            # on a shaky reading is the one thing the clarification loop must
            # not buy: a case that is otherwise complete still goes to a
            # person, exactly as it did before low confidence joined the
            # loop. The loop only changed what happens while the case is
            # still incomplete -- which is where "Hi! what do you want?"
            # lives.
            _log_event(
                logging.INFO,
                "qualification_needs_human_diagnostic",
                reason="below_confidence_threshold_on_complete_case",
                confidence=intent.confidence,
                threshold=threshold,
            )
            return self._result(
                ProcessState.NEEDS_HUMAN,
                ("Intent confidence is below policy or extraction requested review",),
                QualificationReasonCode.LOW_CONFIDENCE,
                intent,
                service,
            )

        rule_outcome = self._qualification_rule_outcome(context, business_dna["qualification"])
        if rule_outcome in {"lost", "disqualified"}:
            return self._result(
                ProcessState.LOST,
                ("A configured qualification rule rejected the lead",),
                QualificationReasonCode.POLICY_REJECTED,
                intent,
                service,
            )
        if rule_outcome in {"needs_human", "human"}:
            return self._result(
                ProcessState.NEEDS_HUMAN,
                ("Configured qualification policy requires human review",),
                QualificationReasonCode.POLICY_REVIEW,
                intent,
                service,
            )

        if intent.urgency is Urgency.HIGH:
            # Decision 2026-08-24 (claude/unit-economics-and-urgency-default.md,
            # variant C): reaching here means "high" was NOT a configured
            # immediate trigger (the check above already handles the case
            # where it is, e.g. a business with escalate_on_high_urgency=True)
            # -- so a high-urgency lead was allowed to complete the ordinary
            # qualification cycle above instead of blocking it. Now that
            # everything required is collected, hand off to a person WITH
            # that full context rather than silently auto-qualifying: speed
            # still matters for a leaking ceiling, it just doesn't require
            # stopping automation to get it. Emergency is unaffected -- it
            # is caught by the trigger check above, unconditionally, before
            # any of this.
            return self._result(
                ProcessState.NEEDS_HUMAN,
                (
                    "Qualification is complete; customer indicated high urgency, "
                    "handing off to a team member with full context for fast follow-up",
                ),
                QualificationReasonCode.URGENT_REQUEST,
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
            reason_codes=(QualificationReasonCode.QUALIFIED,),
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
    def _clarification_attempts(case_metadata: MutableMapping[str, Any] | None) -> int:
        if case_metadata is None:
            return 0
        return int(case_metadata.get("clarification_attempts", 0))

    @staticmethod
    def _record_clarification_attempt(case_metadata: MutableMapping[str, Any] | None, attempts: int) -> None:
        if case_metadata is not None:
            case_metadata["clarification_attempts"] = attempts + 1

    @staticmethod
    def _service_id(service: Mapping[str, Any] | None) -> str | None:
        return str(service["id"]) if service else None

    @staticmethod
    def _result(
        state: ProcessState,
        reasons: tuple[str, ...],
        reason_code: QualificationReasonCode,
        intent: IntentResult,
        service: Mapping[str, Any] | None = None,
    ) -> QualificationResult:
        if state in (ProcessState.NEEDS_HUMAN, ProcessState.LOST):
            # 2026-08-25: this used to log `reasons` -- this file's own fixed
            # strings, except once: the "service is not offered" reason
            # interpolated intent.service_requested, which could hold the
            # customer's own words verbatim (see
            # IntentResult.unsupported_service_name). That was live for eight
            # days under a comment claiming it never happened. `reasons` is
            # free prose by construction and nothing stops the next one being
            # written the same way, so it no longer reaches this log at all --
            # only `reason_code`, which QualificationResult.__post_init__
            # rejects unless it is a QualificationReasonCode member. See that
            # enum's docstring for the guarantee this is standing in for.
            _log_event(
                logging.INFO,
                "qualification_terminal_diagnostic",
                state=state.value,
                reason_code=reason_code.value,
                service_id=QualificationService._service_id(service),
            )
        return QualificationResult(
            qualified=state is ProcessState.QUALIFIED,
            reasons=reasons,
            reason_codes=(reason_code.value,),
            missing_fields=(),
            unanswered_questions=(),
            confidence=intent.confidence,
            recommended_next_state=state,
            requires_human=state is ProcessState.NEEDS_HUMAN,
            booking_allowed=bool(service and service.get("booking_allowed", True) and state is ProcessState.QUALIFIED),
            service_id=QualificationService._service_id(service),
        )
