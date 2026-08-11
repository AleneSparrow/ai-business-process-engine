"""Executable, in-memory Lead Intake and Qualification workflow."""

from dataclasses import replace
from copy import deepcopy
import re
from typing import Any, Mapping
from uuid import uuid4

from src.domain.events import EventType
from src.domain.models import DecisionType, Lead, ProcessCase, ProcessEvent
from src.domain.qualification import (
    CustomerResponse,
    IncomingMessage,
    IntentResult,
    LeadIntakeResult,
    MissingInformationResult,
    QualificationResult,
    Urgency,
)
from src.domain.states import ProcessState

from .decision_router import DecisionRequest
from .customer_response_generator import (
    CustomerResponseGenerator,
    DeterministicCustomerResponseGenerator,
)
from .intent_extractor import IntentExtractor
from .process_engine import ProcessEngine
from .qualification_service import QualificationService
from .question_generator import QuestionGenerator


class LeadIntakeService:
    """Coordinates intake while keeping providers and persistence replaceable."""

    ACTIVE_STATES = frozenset({
        ProcessState.NEW_LEAD,
        ProcessState.CONTACTED,
        ProcessState.QUALIFYING,
        ProcessState.NEEDS_HUMAN,
    })

    def __init__(
        self,
        business_dna: Mapping[str, Any],
        intent_extractor: IntentExtractor,
        question_generator: QuestionGenerator,
        qualification_service: QualificationService | None = None,
        process_engine: ProcessEngine | None = None,
        customer_response_generator: CustomerResponseGenerator | None = None,
    ) -> None:
        self.business_dna = deepcopy(business_dna)
        self.intent_extractor = intent_extractor
        self.question_generator = question_generator
        self.customer_response_generator = (
            customer_response_generator or DeterministicCustomerResponseGenerator()
        )
        self.qualification_service = qualification_service or QualificationService()
        self.process_engine = process_engine or ProcessEngine()
        self._cases: dict[str, ProcessCase] = {}
        self._identity_index: dict[tuple[str, str, str], str] = {}
        self._processed_messages: dict[tuple[str, str, str], LeadIntakeResult] = {}
        self._message_fingerprints: dict[tuple[str, str, str], tuple[object, ...]] = {}
        self._validate_business_dna()

    @property
    def cases(self) -> tuple[ProcessCase, ...]:
        return tuple(self._cases.values())

    def get_case(self, case_id: str) -> ProcessCase:
        try:
            return self._cases[case_id]
        except KeyError as exc:
            raise KeyError(f"unknown case_id: {case_id}") from exc

    def receive(self, message: IncomingMessage) -> LeadIntakeResult:
        self._validate_message_scope(message)
        idempotency_key = (
            message.business_id,
            message.channel.casefold(),
            message.external_message_id,
        )
        previous_result = self._processed_messages.get(idempotency_key)
        if previous_result is not None:
            if self._message_fingerprints[idempotency_key] != self._fingerprint(message):
                raise ValueError("external_message_id was reused with different message content")
            current = self.get_case(previous_result.case_id).current_state
            return replace(previous_result, current_state=current, duplicate=True)

        case = self._find_case(message)
        case_created = case is None
        if case is None:
            lead = Lead(
                lead_id=str(uuid4()),
                name=message.customer_name,
                email=self._normalize_email(message.email),
                phone=self._normalize_phone(message.phone),
            )
            case = ProcessCase(str(uuid4()), message.business_id, lead)
        elif case.current_state not in self.ACTIVE_STATES:
            raise ValueError(f"case {case.case_id} is not active for lead qualification")

        self._assert_identity_consistency(case, message)
        extracted = self.intent_extractor.extract(message, self.business_dna)
        intent = self._merge_intent(case.lead, extracted)
        updated_lead = self._updated_lead(case.lead, message, intent)
        self._validate_identity_available(case, updated_lead)
        qualification = self.qualification_service.evaluate(updated_lead, intent, self.business_dna)
        if case.current_state is ProcessState.NEEDS_HUMAN:
            qualification = self._already_escalated_result(intent, qualification.service_id)
        response = self._create_response(case, message, qualification)

        if case_created:
            self._cases[case.case_id] = case
        case.update_lead(updated_lead)
        self._index_case(case)
        intake_event_id = self._event_id(message, "intake")
        case.record(ProcessEvent(
            EventType.LEAD_INTAKE_RECEIVED,
            event_id=intake_event_id,
            occurred_at=message.timestamp,
            source=message.channel,
            payload={
                "external_message_id": message.external_message_id,
                "customer_name": message.customer_name,
                "phone": message.phone,
                "email": message.email,
                "raw_text": message.raw_text,
            },
        ))
        case.record(ProcessEvent(
            EventType.INTENT_EXTRACTED,
            event_id=self._event_id(message, "intent"),
            source="intent_extractor",
            causation_id=intake_event_id,
            payload={
                "service_requested": intent.service_requested,
                "urgency": intent.urgency.value,
                "customer_location": intent.customer_location,
                "preferred_time": intent.preferred_time,
                "notes": intent.notes,
                "confidence": intent.confidence,
                "requires_human": intent.requires_human,
                "qualification_answers": intent.qualification_answers,
                "ai": intent.ai_metadata,
            },
        ))

        case.record(ProcessEvent(
            EventType.QUALIFICATION_EVALUATED,
            event_id=self._event_id(message, "qualification"),
            source="qualification_service",
            causation_id=intake_event_id,
            payload={
                "qualified": qualification.qualified,
                "reasons": qualification.reasons,
                "missing_fields": qualification.missing_fields,
                "unanswered_questions": qualification.unanswered_questions,
                "confidence": qualification.confidence,
                "recommended_next_state": qualification.recommended_next_state.value,
                "requires_human": qualification.requires_human,
                "booking_allowed": qualification.booking_allowed,
                "service_id": qualification.service_id,
            },
        ))

        self._progress_case(case, message, qualification)
        if response is not None:
            case.record(ProcessEvent(
                EventType.CUSTOMER_RESPONSE_CREATED,
                event_id=self._event_id(message, "response"),
                source="lead_intake_service",
                causation_id=intake_event_id,
                payload={
                    "message_text": response.message_text,
                    "channel": response.channel,
                    "reason": response.reason,
                    "requires_human": response.requires_human,
                    "ai": response.ai_metadata,
                },
            ))

        result = LeadIntakeResult(
            case_id=case.case_id,
            lead_id=case.lead.lead_id,
            current_state=case.current_state,
            qualification=qualification,
            response=response,
            case_created=case_created,
        )
        self._processed_messages[idempotency_key] = result
        self._message_fingerprints[idempotency_key] = self._fingerprint(message)
        return result

    def _progress_case(
        self,
        case: ProcessCase,
        message: IncomingMessage,
        qualification: QualificationResult,
    ) -> None:
        if case.current_state is ProcessState.NEEDS_HUMAN:
            return
        if case.current_state is ProcessState.NEW_LEAD:
            self._transition(case, message, ProcessState.CONTACTED, "contacted")
        if case.current_state is ProcessState.CONTACTED:
            self._transition(case, message, ProcessState.QUALIFYING, "qualifying")
        target = qualification.recommended_next_state
        if target is not ProcessState.QUALIFYING and case.current_state is not target:
            self._transition(case, message, target, "outcome")

    def _transition(
        self,
        case: ProcessCase,
        message: IncomingMessage,
        target: ProcessState,
        stage: str,
    ) -> None:
        decision_type = DecisionType.HUMAN if target is ProcessState.NEEDS_HUMAN else DecisionType.RULE
        requested_target = ProcessState.QUALIFIED if target is ProcessState.NEEDS_HUMAN else target
        self.process_engine.receive(
            case,
            ProcessEvent(
                "LEAD_QUALIFICATION_TRANSITION",
                event_id=self._event_id(message, stage),
                source="lead_intake_service",
                payload={"target_state": target.value, "external_message_id": message.external_message_id},
            ),
            DecisionRequest(decision_type, requested_target),
        )

    def _create_response(
        self,
        case: ProcessCase,
        message: IncomingMessage,
        qualification: QualificationResult,
    ) -> CustomerResponse | None:
        state = qualification.recommended_next_state
        if state is ProcessState.QUALIFYING:
            return self.question_generator.generate(
                MissingInformationResult(
                    qualification.missing_fields,
                    qualification.unanswered_questions,
                ),
                self.business_dna,
                message.channel,
                case.case_id,
            )
        if state is ProcessState.NEEDS_HUMAN:
            text = self.business_dna["human_escalation"]["customer_message"]
            return self.customer_response_generator.generate(
                response_type="human_escalation",
                approved_message=text,
                business_dna=self.business_dna,
                channel=message.channel,
                case_id=case.case_id,
                requires_human=True,
            )
        if state is ProcessState.LOST:
            text = self.business_dna["qualification"]["lost_message"]
            return self.customer_response_generator.generate(
                response_type="not_qualified",
                approved_message=text,
                business_dna=self.business_dna,
                channel=message.channel,
                case_id=case.case_id,
                requires_human=False,
            )
        return None

    def _find_case(self, message: IncomingMessage) -> ProcessCase | None:
        if message.case_id is not None:
            case = self._cases.get(message.case_id)
            if case is None:
                raise KeyError(f"unknown case_id: {message.case_id}")
            if case.business_id != message.business_id:
                raise ValueError("case does not belong to message business_id")
            return case

        candidates: set[str] = set()
        if message.phone:
            case_id = self._identity_index.get((message.business_id, "phone", self._normalize_phone(message.phone)))
            if case_id:
                candidates.add(case_id)
        if message.email:
            case_id = self._identity_index.get((message.business_id, "email", self._normalize_email(message.email)))
            if case_id:
                candidates.add(case_id)
        if len(candidates) > 1:
            raise ValueError("message identifiers resolve to different existing cases")
        return self._cases[next(iter(candidates))] if candidates else None

    def _index_case(self, case: ProcessCase) -> None:
        for identity_type, value in (("phone", case.lead.phone), ("email", case.lead.email)):
            if value:
                key = (case.business_id, identity_type, value)
                existing = self._identity_index.get(key)
                if existing is not None and existing != case.case_id:
                    raise ValueError(f"{identity_type} is already associated with another case")
                self._identity_index[key] = case.case_id

    def _validate_identity_available(self, case: ProcessCase, lead: Lead) -> None:
        for identity_type, value in (("phone", lead.phone), ("email", lead.email)):
            if value:
                existing = self._identity_index.get((case.business_id, identity_type, value))
                if existing is not None and existing != case.case_id:
                    raise ValueError(f"{identity_type} is already associated with another case")

    @staticmethod
    def _assert_identity_consistency(case: ProcessCase, message: IncomingMessage) -> None:
        normalized_phone = LeadIntakeService._normalize_phone(message.phone)
        normalized_email = LeadIntakeService._normalize_email(message.email)
        if case.lead.phone and normalized_phone and case.lead.phone != normalized_phone:
            raise ValueError("incoming phone conflicts with the existing lead")
        if case.lead.email and normalized_email and case.lead.email != normalized_email:
            raise ValueError("incoming email conflicts with the existing lead")

    @staticmethod
    def _updated_lead(lead: Lead, message: IncomingMessage, intent: IntentResult) -> Lead:
        attributes = dict(lead.attributes)
        attributes.update({
            "service_requested": intent.service_requested,
            "customer_location": intent.customer_location,
            "preferred_time": intent.preferred_time,
            "notes": intent.notes,
            "urgency": intent.urgency.value,
            "qualification_answers": dict(intent.qualification_answers),
        })
        return Lead(
            lead_id=lead.lead_id,
            name=lead.name or message.customer_name or intent.customer_name,
            phone=lead.phone or LeadIntakeService._normalize_phone(message.phone or intent.phone),
            email=lead.email or LeadIntakeService._normalize_email(message.email or intent.email),
            attributes=attributes,
        )

    @staticmethod
    def _merge_intent(lead: Lead, current: IntentResult) -> IntentResult:
        previous = lead.attributes
        answers = dict(previous.get("qualification_answers", {}))
        conflict = False
        for question_id, answer in current.qualification_answers.items():
            existing = answers.get(question_id)
            if existing is not None and str(existing).strip().casefold() != str(answer).strip().casefold():
                conflict = True
                continue
            answers[question_id] = answer
        previous_urgency = previous.get("urgency")
        urgency = current.urgency
        if urgency is Urgency.UNKNOWN and isinstance(previous_urgency, str):
            urgency = Urgency(previous_urgency)

        def preserve_strong_fact(current_value: str | None, key: str) -> str | None:
            nonlocal conflict
            existing = previous.get(key)
            if not isinstance(existing, str) or not existing.strip():
                return current_value
            if current_value is not None and existing.strip().casefold() != current_value.strip().casefold():
                conflict = True
            return existing

        for current_value, existing_value, normalizer in (
            (current.phone, lead.phone, LeadIntakeService._normalize_phone),
            (current.email, lead.email, LeadIntakeService._normalize_email),
        ):
            if current_value and existing_value and normalizer(current_value) != existing_value:
                conflict = True
        if current.customer_name and lead.name and current.customer_name.strip().casefold() != lead.name.strip().casefold():
            conflict = True
        return IntentResult(
            service_requested=preserve_strong_fact(current.service_requested, "service_requested"),
            urgency=urgency,
            customer_location=preserve_strong_fact(current.customer_location, "customer_location"),
            preferred_time=preserve_strong_fact(current.preferred_time, "preferred_time"),
            notes=current.notes or previous.get("notes"),
            confidence=current.confidence,
            requires_human=current.requires_human or conflict,
            qualification_answers=answers,
            ai_metadata=current.ai_metadata,
            customer_name=current.customer_name,
            phone=current.phone,
            email=current.email,
        )

    def _validate_business_dna(self) -> None:
        configured_id = self.business_dna.get("business", {}).get("id")
        if not isinstance(configured_id, str) or not configured_id:
            raise ValueError("Business DNA must contain business.id")
        communication = self.business_dna.get("communication", {})
        channels = communication.get("channels", [])
        if not isinstance(channels, list) or not channels:
            raise ValueError("Business DNA must enable at least one communication channel")
        if communication.get("default_channel") not in channels:
            raise ValueError("default_channel must be one of the enabled channels")
        language = communication.get("language", "English")
        if not isinstance(language, str) or not language.strip():
            raise ValueError("communication.language must be a non-empty string when configured")

        customer_information = self.business_dna.get("customer_information", {})
        required_fields = customer_information.get("required_fields", [])
        optional_fields = customer_information.get("optional_fields", [])
        field_questions = customer_information.get("field_questions", {})
        if set(required_fields).intersection(optional_fields):
            raise ValueError("required_fields and optional_fields must not overlap")
        missing_prompts = set(required_fields).difference(field_questions)
        if missing_prompts:
            raise ValueError(f"required fields have no configured questions: {sorted(missing_prompts)}")

        areas = self.business_dna.get("service_areas", [])
        area_ids = [area.get("id") for area in areas]
        if len(area_ids) != len(set(area_ids)):
            raise ValueError("service area IDs must be unique")

        service_ids: set[str] = set()
        term_owners: dict[str, str] = {}
        for service in self.business_dna.get("services", []):
            service_id = service.get("id")
            if service_id in service_ids:
                raise ValueError("service IDs must be unique")
            service_ids.add(service_id)
            unknown_areas = set(service.get("service_area_ids", [])).difference(area_ids)
            if unknown_areas:
                raise ValueError(f"service references unknown service areas: {sorted(unknown_areas)}")
            question_ids = [question.get("id") for question in service.get("qualification_questions", [])]
            if len(question_ids) != len(set(question_ids)):
                raise ValueError(f"qualification question IDs must be unique within service: {service_id}")
            terms = (service_id, service.get("name"), *service.get("intake_keywords", []))
            for term in terms:
                normalized = str(term).strip().casefold()
                owner = term_owners.get(normalized)
                if owner is not None and owner != service_id:
                    raise ValueError(f"service intake term is ambiguous: {term}")
                term_owners[normalized] = service_id

        permissions = self.business_dna.get("ai_permissions", {})
        overlap = set(permissions.get("allowed", [])).intersection(permissions.get("forbidden", []))
        if overlap:
            raise ValueError(f"AI permissions cannot be both allowed and forbidden: {sorted(overlap)}")

    def _validate_message_scope(self, message: IncomingMessage) -> None:
        if message.business_id != self.business_dna["business"]["id"]:
            raise ValueError("message business_id does not match Business DNA")
        channels = self.business_dna["communication"]["channels"]
        if message.channel not in channels:
            raise ValueError(f"channel is not enabled in Business DNA: {message.channel}")

    @staticmethod
    def _already_escalated_result(intent: IntentResult, service_id: str | None) -> QualificationResult:
        return QualificationResult(
            qualified=False,
            reasons=("Case is already awaiting human review",),
            missing_fields=(),
            unanswered_questions=(),
            confidence=intent.confidence,
            recommended_next_state=ProcessState.NEEDS_HUMAN,
            requires_human=True,
            booking_allowed=False,
            service_id=service_id,
        )

    @staticmethod
    def _normalize_email(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("email is not valid")
        return normalized

    @staticmethod
    def _normalize_phone(value: str | None) -> str | None:
        if not value:
            return None
        prefix = "+" if value.strip().startswith("+") else ""
        digits = "".join(character for character in value if character.isdigit())
        if not 7 <= len(digits) <= 15:
            raise ValueError("phone must contain between 7 and 15 digits")
        return f"{prefix}{digits}"

    @staticmethod
    def _fingerprint(message: IncomingMessage) -> tuple[object, ...]:
        return (
            message.raw_text,
            message.timestamp,
            message.customer_name,
            LeadIntakeService._normalize_phone(message.phone),
            LeadIntakeService._normalize_email(message.email),
            message.case_id,
        )

    @staticmethod
    def _event_id(message: IncomingMessage, stage: str) -> str:
        return f"lead-intake:{message.business_id}:{message.channel}:{message.external_message_id}:{stage}"
