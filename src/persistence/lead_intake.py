"""Transactionally persisted Lead Intake and Qualification orchestration."""

import hashlib
import json
from datetime import timezone
from typing import Any, Mapping
from uuid import uuid4

from src.domain.events import EventType
from src.domain.models import Lead, ProcessCase, ProcessEvent
from src.domain.qualification import (
    CustomerResponse,
    IncomingMessage,
    IntentResult,
    LeadIntakeResult,
    QualificationResult,
)
from src.domain.states import ProcessState
from src.engine.intent_extractor import IntentExtractor
from src.engine.lead_intake import LeadIntakeService
from src.engine.process_engine import ProcessEngine
from src.engine.qualification_service import QualificationService
from src.engine.question_generator import QuestionGenerator

from .errors import IdempotencyInProgressError
from .repositories import ClaimStatus, UnitOfWork, UnitOfWorkFactory


class PersistentLeadIntakeService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        intent_extractor: IntentExtractor,
        question_generator: QuestionGenerator,
        qualification_service: QualificationService | None = None,
        process_engine: ProcessEngine | None = None,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.intent_extractor = intent_extractor
        self.question_generator = question_generator
        self.qualification_service = qualification_service or QualificationService()
        self.process_engine = process_engine or ProcessEngine()

    def receive(self, message: IncomingMessage) -> LeadIntakeResult:
        fingerprint = self.fingerprint(message)
        channel = message.channel.casefold()
        with self.unit_of_work_factory() as uow:
            if uow.businesses.get(message.business_id) is None:
                raise KeyError(f"unknown business_id: {message.business_id}")
            claim_status, claim = uow.idempotency.claim(
                message.business_id, channel, message.external_message_id, fingerprint
            )
            if claim_status is ClaimStatus.COMPLETED:
                if claim.result is None or claim.case_id is None:
                    raise IdempotencyInProgressError("completed message has no persisted result")
                case = uow.cases.get(message.business_id, claim.case_id)
                if case is None:
                    raise RuntimeError("idempotency result references a missing tenant case")
                return self._deserialize_result(claim.result, duplicate=True)

            dna_version = uow.business_dna.get_active(message.business_id)
            if dna_version is None:
                raise RuntimeError(f"business has no active Business DNA: {message.business_id}")
            workflow = LeadIntakeService(
                self._plain_json(dna_version.configuration),
                self.intent_extractor,
                self.question_generator,
                self.qualification_service,
                self.process_engine,
            )
            workflow._validate_message_scope(message)

            case, case_created, lead_created = self._resolve_case(uow, workflow, message)
            if case.current_state not in workflow.ACTIVE_STATES:
                raise ValueError(f"case {case.case_id} is not active for lead qualification")
            workflow._assert_identity_consistency(case, message)

            extracted = self.intent_extractor.extract(message, workflow.business_dna)
            intent = workflow._merge_intent(case.lead, extracted)
            updated_lead = workflow._updated_lead(case.lead, message, intent)
            qualification = self.qualification_service.evaluate(updated_lead, intent, workflow.business_dna)
            if case.current_state is ProcessState.NEEDS_HUMAN:
                qualification = workflow._already_escalated_result(intent, qualification.service_id)
            response = workflow._create_response(case, message, qualification)

            existing_event_count = len(case.event_history)
            expected_version = case.version
            case.update_lead(updated_lead)
            self._record_business_events(case, message, intent, qualification, dna_version.version)
            workflow._progress_case(case, message, qualification)
            if response is not None:
                self._record_response(case, message, response)

            if lead_created:
                uow.leads.add(message.business_id, updated_lead, case.created_at)
            else:
                uow.leads.save(message.business_id, updated_lead, case.updated_at)
            if case_created:
                uow.cases.add(case)
            else:
                uow.cases.save(case, expected_version)
            new_events = case.event_history[existing_event_count:]
            uow.events.add_many(message.business_id, case.case_id, new_events)

            result = LeadIntakeResult(
                case.case_id,
                updated_lead.lead_id,
                case.current_state,
                qualification,
                response,
                case_created,
            )
            uow.idempotency.complete(
                message.business_id,
                channel,
                message.external_message_id,
                case.case_id,
                self._serialize_result(result),
            )
            uow.commit()
            return result

    @staticmethod
    def fingerprint(message: IncomingMessage) -> str:
        canonical = json.dumps({
            "business_id": message.business_id,
            "channel": message.channel.casefold(),
            "external_message_id": message.external_message_id,
            "raw_text": message.raw_text,
            "timestamp": message.timestamp.astimezone(timezone.utc).isoformat(),
            "customer_name": message.customer_name,
            "phone": LeadIntakeService._normalize_phone(message.phone),
            "email": LeadIntakeService._normalize_email(message.email),
            "case_id": message.case_id,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _plain_json(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): PersistentLeadIntakeService._plain_json(item) for key, item in value.items()}
        if isinstance(value, tuple | list):
            return [PersistentLeadIntakeService._plain_json(item) for item in value]
        return value

    @staticmethod
    def _resolve_case(
        uow: UnitOfWork,
        workflow: LeadIntakeService,
        message: IncomingMessage,
    ) -> tuple[ProcessCase, bool, bool]:
        if message.case_id:
            case = uow.cases.get(message.business_id, message.case_id)
            if case is None:
                raise KeyError(f"unknown case_id for business: {message.case_id}")
            return case, False, False

        phone = workflow._normalize_phone(message.phone)
        email = workflow._normalize_email(message.email)
        lead = uow.leads.find_by_identity(message.business_id, phone, email)
        lead_created = lead is None
        if lead is None:
            lead = Lead(str(uuid4()), message.customer_name, email, phone)
        case = None if lead_created else uow.cases.find_active_for_lead(message.business_id, lead.lead_id)
        case_created = case is None
        if case is None:
            case = ProcessCase(str(uuid4()), message.business_id, lead)
        return case, case_created, lead_created

    @staticmethod
    def _record_business_events(
        case: ProcessCase,
        message: IncomingMessage,
        intent: IntentResult,
        qualification: QualificationResult,
        business_dna_version: int,
    ) -> None:
        intake_event_id = LeadIntakeService._event_id(message, "intake")
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
            event_id=LeadIntakeService._event_id(message, "intent"),
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
            },
        ))
        case.record(ProcessEvent(
            EventType.QUALIFICATION_EVALUATED,
            event_id=LeadIntakeService._event_id(message, "qualification"),
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
                "business_dna_version": business_dna_version,
            },
        ))

    @staticmethod
    def _record_response(case: ProcessCase, message: IncomingMessage, response: CustomerResponse) -> None:
        case.record(ProcessEvent(
            EventType.CUSTOMER_RESPONSE_CREATED,
            event_id=LeadIntakeService._event_id(message, "response"),
            source="lead_intake_service",
            causation_id=LeadIntakeService._event_id(message, "intake"),
            payload={
                "message_text": response.message_text,
                "channel": response.channel,
                "reason": response.reason,
                "requires_human": response.requires_human,
            },
        ))

    @staticmethod
    def _serialize_result(result: LeadIntakeResult) -> dict[str, Any]:
        qualification = result.qualification
        response = result.response
        return {
            "case_id": result.case_id,
            "lead_id": result.lead_id,
            "current_state": result.current_state.value,
            "case_created": result.case_created,
            "qualification": {
                "qualified": qualification.qualified,
                "reasons": list(qualification.reasons),
                "missing_fields": list(qualification.missing_fields),
                "unanswered_questions": list(qualification.unanswered_questions),
                "confidence": qualification.confidence,
                "recommended_next_state": qualification.recommended_next_state.value,
                "requires_human": qualification.requires_human,
                "booking_allowed": qualification.booking_allowed,
                "service_id": qualification.service_id,
            },
            "response": None if response is None else {
                "message_text": response.message_text,
                "channel": response.channel,
                "reason": response.reason,
                "related_case_id": response.related_case_id,
                "requires_human": response.requires_human,
            },
        }

    @staticmethod
    def _deserialize_result(
        value: Mapping[str, Any],
        *,
        duplicate: bool,
    ) -> LeadIntakeResult:
        qualification_value = value["qualification"]
        qualification = QualificationResult(
            qualified=qualification_value["qualified"],
            reasons=tuple(qualification_value["reasons"]),
            missing_fields=tuple(qualification_value["missing_fields"]),
            unanswered_questions=tuple(qualification_value["unanswered_questions"]),
            confidence=qualification_value["confidence"],
            recommended_next_state=ProcessState(qualification_value["recommended_next_state"]),
            requires_human=qualification_value["requires_human"],
            booking_allowed=qualification_value["booking_allowed"],
            service_id=qualification_value.get("service_id"),
        )
        response_value = value.get("response")
        response = CustomerResponse(**response_value) if response_value else None
        return LeadIntakeResult(
            value["case_id"],
            value["lead_id"],
            ProcessState(value["current_state"]),
            qualification,
            response,
            value["case_created"],
            duplicate,
        )
