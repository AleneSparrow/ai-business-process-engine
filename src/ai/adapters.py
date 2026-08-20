"""Validated adapters from structured AI output to existing engine protocols."""

from dataclasses import replace
import json
import logging
import re
from typing import Any, Mapping, Sequence

from src.domain.qualification import (
    CustomerResponse,
    CustomerTone,
    IncomingMessage,
    IntentResult,
    MissingInformationResult,
    Urgency,
)
from src.domain.conversations import MessageRole

from .errors import AIConfigurationError, AIInvalidOutputError
from .models import (
    AIInvocationMetadata,
    AIRequest,
    ClarificationOutput,
    CustomerMessageOutput,
    IntentOutput,
    ReassuranceOutput,
    UniversalReassuranceOutput,
)
from .prompts import (
    clarification_prompt,
    customer_response_prompt,
    intent_prompt,
    reassurance_prompt,
    universal_reassurance_prompt,
)
from .provider import StructuredAIProvider

# TEMPORARY diagnostic logging (2026-08-17): the qualification threshold
# check (`intent.requires_human or intent.confidence < threshold`) has no
# visibility today when it fires on the AI's own judgment rather than on a
# caught AIInvalidOutputError -- both look identical from the outside
# (resulting_state=NEEDS_HUMAN with no error). All fields below are safe to
# log: confidence/requires_human/urgency are model-internal signals, and
# service_requested is a catalog ID, never customer-submitted free text.
#
# NOTE: deliberately not importing `src.api.observability.log_event` here --
# src/api/app.py imports src.ai.runtime, which imports this module, so
# importing anything under `src.api` from here (even transitively, via
# package __init__ side effects) risks a circular import when this module
# is the first one touched (e.g. `from src.ai.adapters import ...` in a
# test, before anything has imported src.api). Logging directly with the
# same "uvicorn.error" logger name keeps identical log output without that
# dependency direction.
_LOGGER = logging.getLogger("uvicorn.error")


def _log_event(level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: value for key, value in fields.items() if value is not None}}
    _LOGGER.log(level, json.dumps(payload, separators=(",", ":"), default=str))


_UNSAFE_CUSTOMER_COMMITMENT = re.compile(
    r"(?:\b(?:discount|refund|waive|complimentary|guarantee|promise)\b|"
    r"\bfree\s+(?:service|visit|estimate|consultation|upgrade)\b|"
    r"\bat no (?:charge|cost)\b|[$€£]\s*\d|\b\d{1,3}\s*%)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{5,}\d)(?!\w)")


def _communication(business_dna: Mapping[str, object]) -> Mapping[str, object]:
    value = business_dna.get("communication", {})
    return value if isinstance(value, Mapping) else {}


def _audit(metadata: AIInvocationMetadata, *, confidence: float | None = None) -> Mapping[str, object]:
    return metadata.as_audit_dict(confidence=confidence)


def _invalid_metadata(metadata: AIInvocationMetadata) -> AIInvocationMetadata:
    return replace(metadata, success=False, category="invalid_output")


def _safe_message(text: str, business_dna: Mapping[str, object]) -> bool:
    if _UNSAFE_CUSTOMER_COMMITMENT.search(text):
        return False
    permissions = business_dna.get("ai_permissions", {})
    forbidden = permissions.get("forbidden", []) if isinstance(permissions, Mapping) else []
    normalized_text = text.casefold()
    for action in forbidden if isinstance(forbidden, list) else []:
        if isinstance(action, str) and action.replace("_", " ").casefold() in normalized_text:
            return False
    return True


def _require_permissions(business_dna: Mapping[str, object], *required: str) -> None:
    permissions = business_dna.get("ai_permissions", {})
    allowed = permissions.get("allowed", []) if isinstance(permissions, Mapping) else []
    allowed_set = (
        {value for value in allowed if isinstance(value, str)}
        if isinstance(allowed, list)
        else set()
    )
    missing = set(required).difference(allowed_set)
    if missing:
        raise AIConfigurationError("Business DNA does not permit the requested AI capability")


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE))


class AIIntentExtractor:
    def __init__(self, provider: StructuredAIProvider) -> None:
        self.provider = provider

    def extract(self, message: IncomingMessage, business_dna: Mapping[str, object]) -> IntentResult:
        _require_permissions(business_dna, "classify_intent", "extract_customer_details")
        services_context: list[dict[str, object]] = []
        services = business_dna.get("services", [])
        if isinstance(services, list):
            for service in services:
                if not isinstance(service, Mapping):
                    continue
                questions: list[dict[str, str]] = []
                for question in service.get("qualification_questions", []):
                    if not isinstance(question, Mapping):
                        continue
                    question_id = question.get("id")
                    prompt = question.get("prompt")
                    if isinstance(question_id, str) and isinstance(prompt, str):
                        questions.append({"id": question_id, "prompt": prompt})
                services_context.append({
                    "id": service.get("id"),
                    "name": service.get("name"),
                    "aliases": service.get("intake_keywords", []),
                    "qualification_questions": questions,
                })
        # TEMPORARY diagnostic (2026-08-17): services_context is catalog
        # configuration (ids/names/configured alias keywords/question ids),
        # never customer content -- safe to log. Investigating whether the
        # "supported service without customer evidence" rejections are an
        # AI bug or a business-DNA catalog gap (narrow intake_keywords).
        _log_event(
            logging.INFO,
            "services_context_diagnostic",
            services=[
                {"id": s.get("id"), "name": s.get("name"), "aliases": s.get("aliases")}
                for s in services_context
            ],
        )
        prompt = intent_prompt(
            context={
                "services": services_context,
                "human_escalation_triggers": business_dna.get("human_escalation", {}).get(
                    "triggers", []
                ) if isinstance(business_dna.get("human_escalation"), Mapping) else [],
                "conversation": self._conversation_context(message),
            },
            customer_message=message.raw_text,
        )
        request = AIRequest(
            prompt.identifier,
            prompt.version,
            "intent_extraction",
            prompt.system,
            prompt.user,
            IntentOutput,
        )
        try:
            result = self.provider.generate(request)
            output = result.output
            known_facts = (
                message.conversation_context.known_facts
                if message.conversation_context is not None
                else {}
            )
            service_requested = self._resolve_service(
                output,
                services_context,
                message.raw_text,
                known_facts.get("service_requested"),
            )
            customer_location = self._evidenced(
                output.customer_location,
                message.raw_text,
                "location",
                known_facts.get("customer_location"),
            )
            preferred_time = self._evidenced(
                output.preferred_time,
                message.raw_text,
                "preferred time",
                known_facts.get("preferred_time"),
            )
            effective_service = service_requested or known_facts.get("service_requested")
            allowed_question_ids = {
                str(question["id"])
                for service in services_context
                if service.get("id") == effective_service
                for question in service.get("qualification_questions", [])
                if isinstance(question, Mapping) and isinstance(question.get("id"), str)
            }
            answers: dict[str, str] = {}
            for answer in output.qualification_answers:
                if answer.question_id not in allowed_question_ids or answer.question_id in answers:
                    raise AIInvalidOutputError("AI returned an unauthorized qualification answer")
                answer_value = answer.answer.strip()
                if not _contains_term(message.raw_text, answer_value):
                    # TEMPORARY diagnostic (2026-08-17): question_id is a
                    # catalog ID (safe); loosely_matches is a boolean
                    # computed from a punctuation/casing-normalized
                    # comparison -- neither ever logs the actual customer-
                    # derived text. This tells us whether the miss is a
                    # reformatting issue (like the earlier phone-number bug)
                    # or the AI adding/paraphrasing content the customer
                    # never said.
                    normalize = lambda text: re.sub(  # noqa: E731
                        r"\s+", " ", re.sub(r"[^\w\s]", "", text).casefold()
                    ).strip()
                    loosely_matches = bool(normalize(answer_value)) and normalize(answer_value) in normalize(
                        message.raw_text
                    )
                    raise AIInvalidOutputError(
                        "AI returned a qualification answer without customer evidence "
                        f"(question_id={answer.question_id}, loosely_matches_normalized={loosely_matches})"
                    )
                answers[answer.question_id] = answer_value
            final_requires_human = output.requires_human or self._configured_trigger_matches(
                message.raw_text, business_dna
            )
            _log_event(
                logging.INFO,
                "intent_extracted_diagnostic",
                service_requested=service_requested,
                confidence=output.confidence,
                ai_requires_human=output.requires_human,
                trigger_matched=final_requires_human and not output.requires_human,
                urgency=output.urgency.value if output.urgency is not None else None,
                prompt_version=prompt.version,
            )
            return IntentResult(
                service_requested=service_requested,
                urgency=output.urgency,
                customer_location=customer_location,
                preferred_time=preferred_time,
                notes=self._notes(output.notes, message.raw_text),
                confidence=output.confidence,
                requires_human=final_requires_human,
                qualification_answers=answers,
                ai_metadata=_audit(result.metadata, confidence=output.confidence),
                customer_name=self._evidenced(output.customer_name, message.raw_text, "name"),
                phone=self._phone_evidenced(output.phone, message.raw_text),
                email=self._evidenced(output.email, message.raw_text, "email"),
                objection_phrase=self._evidenced(
                    output.objection_phrase, message.raw_text, "objection phrase"
                ),
                customer_tone=output.customer_tone,
            )
        except AIInvalidOutputError as exc:
            # Same diagnostic as the success path above, for the collapse-to-
            # NEEDS_HUMAN case: `str(exc)` here is always one of this file's
            # own fixed messages (e.g. "AI returned phone without customer
            # evidence") -- never customer-submitted content.
            _log_event(logging.INFO, "intent_extraction_invalid_diagnostic", reason=str(exc))
            metadata = exc.metadata
            if metadata is None and "result" in locals():
                metadata = _invalid_metadata(result.metadata)
            audit = _audit(metadata, confidence=0.0) if metadata is not None else {
                "provider": "unknown",
                "model": "unknown",
                "prompt_id": prompt.identifier,
                "prompt_version": prompt.version,
                "decision_type": "intent_extraction",
                "latency_ms": None,
                "success": False,
                "category": "invalid_output",
                "attempts": 1,
                "confidence": 0.0,
            }
            return IntentResult(
                urgency=Urgency.UNKNOWN,
                confidence=0.0,
                requires_human=True,
                ai_metadata=audit,
            )

    @staticmethod
    def _resolve_service(
        output: IntentOutput,
        services: list[dict[str, object]],
        customer_message: str,
        known_service: object = None,
    ) -> str | None:
        if output.unsupported_service:
            name = AIIntentExtractor._clean(output.unsupported_service_name)
            service_id_also_set = output.service_id is not None
            name_is_none = name is None
            evidenced = name is not None and _contains_term(customer_message, name)
            if service_id_also_set or name_is_none or not evidenced:
                # TEMPORARY diagnostic (2026-08-17): three independent
                # failure modes collapsed into one message before -- these
                # booleans (plus a punctuation/casing-normalized loose-match
                # check, same technique as the qualification-answer
                # diagnostic) say which one fired, without logging the
                # actual customer-derived unsupported_service_name text.
                loosely_matches = False
                if name is not None:
                    normalize = lambda text: re.sub(  # noqa: E731
                        r"\s+", " ", re.sub(r"[^\w\s]", "", text).casefold()
                    ).strip()
                    loosely_matches = bool(normalize(name)) and normalize(name) in normalize(
                        customer_message
                    )
                raise AIInvalidOutputError(
                    "AI returned an invalid unsupported service "
                    f"(service_id_also_set={service_id_also_set}, name_is_none={name_is_none}, "
                    f"evidenced={evidenced}, loosely_matches_normalized={loosely_matches})"
                )
            return name
        if output.unsupported_service_name is not None:
            raise AIInvalidOutputError("AI returned contradictory service fields")
        requested = AIIntentExtractor._clean(output.service_id)
        if requested is None:
            return None
        normalized = requested.casefold()
        matches: list[tuple[str, tuple[str, ...]]] = []
        for service in services:
            terms = [service.get("id"), service.get("name"), *service.get("aliases", [])]
            normalized_terms = tuple(
                str(term).strip().casefold() for term in terms if isinstance(term, str)
            )
            if normalized in set(normalized_terms):
                service_id = service.get("id")
                if isinstance(service_id, str):
                    matches.append((service_id, normalized_terms))
        unique_ids = {service_id for service_id, _ in matches}
        if len(unique_ids) != 1:
            raise AIInvalidOutputError("AI returned a service outside the supplied catalog")
        customer_text = customer_message.casefold()
        known_matches = isinstance(known_service, str) and known_service == matches[0][0]
        # A business with exactly one configured service has nothing to
        # disambiguate: `output.service_id` already had to resolve, via the
        # lookup above, to that one real catalog entry -- the AI cannot
        # invent an arbitrary service here, only select the sole option
        # that actually exists. Live target-audience testing found this
        # check otherwise forces every self-serve business with a single
        # generic service (the common case for a solo practice) to
        # escalate almost every real customer message, since intake
        # keywords default to just the service's own name (see
        # business_dna_builder.py) and there is currently no UI to add
        # synonyms. For a business with two or more services the check
        # stays exactly as strict as before -- distinguishing between
        # several real options is exactly what it's for.
        single_service_catalog = len(services) == 1
        if (
            not known_matches
            and not single_service_catalog
            and not any(_contains_term(customer_text, term) for _, terms in matches for term in terms)
        ):
            raise AIInvalidOutputError("AI returned a supported service without customer evidence")
        return matches[0][0]

    @staticmethod
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _notes(value: str | None, customer_message: str) -> str | None:
        cleaned = AIIntentExtractor._clean(value)
        if cleaned is None or cleaned.casefold() == customer_message.strip().casefold():
            return None
        redacted = _EMAIL.sub("[contact redacted]", cleaned)
        redacted = _PHONE.sub("[contact redacted]", redacted)
        return redacted

    @staticmethod
    def _evidenced(
        value: str | None,
        customer_message: str,
        field_name: str,
        known_value: object = None,
    ) -> str | None:
        cleaned = AIIntentExtractor._clean(value)
        is_known = isinstance(known_value, str) and known_value.strip().casefold() == (
            cleaned.casefold() if cleaned is not None else ""
        )
        if cleaned is not None and not is_known and not _contains_term(customer_message, cleaned):
            raise AIInvalidOutputError(f"AI returned {field_name} without customer evidence")
        return cleaned

    @staticmethod
    def _phone_evidenced(value: str | None, customer_message: str) -> str | None:
        """Same anti-hallucination guarantee as `_evidenced`, but digit-based
        rather than an exact substring match. Live finding: the customer's
        own literal punctuation/spacing (`555-987-6543` vs `(555) 987-6543`
        vs `555.987.6543`) is not something the prompt's "extract verbatim"
        instruction reliably survives -- a harmlessly reformatted phone
        number failed the strict `_evidenced` check, which collapsed the
        *entire* intent result to confidence=0.0 and forced NEEDS_HUMAN on
        an ordinary customer answering "what's your phone number?". Every
        digit still has to come from the customer's own message -- this
        does not relax the guarantee that the AI cannot invent a phone
        number, only which punctuation counts as the "same" one."""
        cleaned = AIIntentExtractor._clean(value)
        if cleaned is None:
            return None
        cleaned_digits = re.sub(r"\D", "", cleaned)
        message_digits = re.sub(r"\D", "", customer_message)
        candidates = {cleaned_digits}
        # A model-added US country-code digit the customer didn't type is
        # still evidence-backed for the other 10 digits.
        if len(cleaned_digits) == 11 and cleaned_digits.startswith("1"):
            candidates.add(cleaned_digits[1:])
        if not any(candidate and candidate in message_digits for candidate in candidates):
            raise AIInvalidOutputError("AI returned phone without customer evidence")
        return cleaned

    @staticmethod
    def _conversation_context(message: IncomingMessage) -> Mapping[str, object]:
        context = message.conversation_context
        if context is None:
            return {}
        return {
            "recent_messages": [
                {"role": item.role.value, "text": AIIntentExtractor._plain_value(item.text)}
                for item in context.recent_messages
                if item.role in {MessageRole.CUSTOMER, MessageRole.ASSISTANT}
            ],
            "known_facts": AIIntentExtractor._plain_value(context.known_facts),
            "unresolved_items": list(context.unresolved_items),
            "current_state": context.current_state,
        }

    @staticmethod
    def _plain_value(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): AIIntentExtractor._plain_value(item) for key, item in value.items()}
        if isinstance(value, tuple | list):
            return [AIIntentExtractor._plain_value(item) for item in value]
        if isinstance(value, str):
            return _PHONE.sub("[contact redacted]", _EMAIL.sub("[contact redacted]", value))
        return value

    @staticmethod
    def _configured_trigger_matches(
        customer_message: str,
        business_dna: Mapping[str, object],
    ) -> bool:
        escalation = business_dna.get("human_escalation", {})
        triggers = escalation.get("triggers", []) if isinstance(escalation, Mapping) else []
        return any(
            _contains_term(customer_message, trigger.replace("_", " "))
            for trigger in triggers
            if isinstance(trigger, str) and trigger.strip()
        )


class AIQuestionGenerator:
    def __init__(self, provider: StructuredAIProvider) -> None:
        self.provider = provider

    def generate(
        self,
        missing: MissingInformationResult,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        customer_message: str = "",
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse:
        _require_permissions(business_dna, "draft_message")
        customer_information = business_dna.get("customer_information", {})
        field_questions = (
            customer_information.get("field_questions", {})
            if isinstance(customer_information, Mapping)
            else {}
        )
        allowed_items: list[dict[str, str]] = []
        for field_name in missing.missing_fields:
            prompt_text = (
                field_questions.get(field_name)
                if isinstance(field_questions, Mapping)
                else None
            )
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                raise ValueError(
                    f"Business DNA has no question configured for required field: {field_name}"
                )
            allowed_items.append({"id": f"field:{field_name}", "question": prompt_text.strip()})
        for index, prompt_text in enumerate(missing.unanswered_questions):
            allowed_items.append({"id": f"qualification:{index}", "question": prompt_text.strip()})
        if not allowed_items:
            raise ValueError("cannot generate a missing-information response without questions")
        communication = _communication(business_dna)
        prompt = clarification_prompt(
            context={
                "language": communication.get("language", "English"),
                "tone": communication.get("tone"),
                "customer_tone": customer_tone.value,
                "channel": channel,
                "allowed_items": allowed_items,
            },
            # Live finding (2026-08-20): this used to be hardcoded to "" --
            # the model never actually saw the customer's own message, only
            # the pre-built allowed_items questions, so it had nothing to
            # mirror the tone/form of even though the prompt already claimed
            # this field was for "avoiding awkward repetition". Passing the
            # real message is what makes tone adaptation (see
            # TONE_ADAPTATION_INSTRUCTION) actually have something to adapt to.
            customer_message=customer_message,
        )
        request = AIRequest(
            prompt.identifier,
            prompt.version,
            "question_generation",
            prompt.system,
            prompt.user,
            ClarificationOutput,
        )
        result = self.provider.generate(request)
        expected_ids = [item["id"] for item in allowed_items]
        if result.output.addressed_items != expected_ids or not _safe_message(
            result.output.message_text, business_dna
        ):
            raise AIInvalidOutputError(
                "AI clarification introduced an unauthorized item or commitment",
                metadata=_invalid_metadata(result.metadata),
            )
        return CustomerResponse(
            result.output.message_text.strip(),
            channel,
            "missing_information",
            case_id,
            ai_metadata=_audit(result.metadata),
        )


class AICustomerResponseGenerator:
    def __init__(self, provider: StructuredAIProvider) -> None:
        self.provider = provider

    def generate(
        self,
        *,
        response_type: str,
        approved_message: str,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        requires_human: bool,
        customer_message: str = "",
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse:
        _require_permissions(business_dna, "draft_message")
        if response_type not in {"not_qualified", "human_escalation"}:
            raise ValueError("unsupported AI customer response type")
        communication = _communication(business_dna)
        prompt = customer_response_prompt(
            context={
                "response_type": response_type,
                "approved_message": approved_message,
                "language": communication.get("language", "English"),
                "tone": communication.get("tone"),
                "customer_tone": customer_tone.value,
                "channel": channel,
            },
            customer_message=customer_message,
        )
        request = AIRequest(
            prompt.identifier,
            prompt.version,
            "customer_response_generation",
            prompt.system,
            prompt.user,
            CustomerMessageOutput,
        )
        result = self.provider.generate(request)
        if result.output.response_type != response_type or not _safe_message(
            result.output.message_text, business_dna
        ):
            raise AIInvalidOutputError(
                "AI customer response changed the approved decision or made an unsafe commitment",
                metadata=_invalid_metadata(result.metadata),
            )
        return CustomerResponse(
            result.output.message_text.strip(),
            channel,
            response_type,
            case_id,
            requires_human,
            _audit(result.metadata),
        )


class AIReassuranceResponseGenerator:
    """AI selects and rephrases exactly one owner-approved objection_responses
    entry -- it is never permitted to draft new reassurance content. Selection
    is validated in code against the closed set of configured entries, the
    same anti-hallucination guarantee AIQuestionGenerator applies to
    addressed_items."""

    def __init__(self, provider: StructuredAIProvider) -> None:
        self.provider = provider

    def generate(
        self,
        objection_phrase: str,
        approved_responses: Sequence[Mapping[str, object]],
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse:
        _require_permissions(business_dna, "draft_message")
        if not approved_responses:
            raise ValueError("cannot generate a reassurance response without any configured entries")
        entries: list[dict[str, str]] = []
        for entry in approved_responses:
            trigger = entry.get("trigger_description")
            response = entry.get("approved_response")
            if not isinstance(trigger, str) or not isinstance(response, str):
                raise ValueError("configured objection_responses entry is missing required text")
            entries.append({"trigger_description": trigger, "approved_response": response})
        communication = _communication(business_dna)
        prompt = reassurance_prompt(
            context={
                "objection_phrase": objection_phrase,
                "approved_objection_responses": entries,
                "language": communication.get("language", "English"),
                "tone": communication.get("tone"),
                "customer_tone": customer_tone.value,
                "channel": channel,
            },
            customer_message=objection_phrase,
        )
        request = AIRequest(
            prompt.identifier,
            prompt.version,
            "reassurance_response_generation",
            prompt.system,
            prompt.user,
            ReassuranceOutput,
        )
        result = self.provider.generate(request)
        selected = result.output.selected_trigger_description
        matched = next(
            (entry for entry in entries if entry["trigger_description"] == selected), None
        )
        if matched is None or not _safe_message(result.output.message_text, business_dna):
            raise AIInvalidOutputError(
                "AI reassurance response selected an unconfigured entry or made an unsafe commitment",
                metadata=_invalid_metadata(result.metadata),
            )
        return CustomerResponse(
            result.output.message_text.strip(),
            channel,
            "objection_reassurance",
            case_id,
            ai_metadata=_audit(result.metadata),
        )


class AIUniversalReassuranceResponseGenerator:
    """Zero-config counterpart to AIReassuranceResponseGenerator -- used
    whenever the business has not authored any qualification.
    objection_responses entries (see LeadIntakeService._with_reassurance for
    how the two are chosen; the owner-authored path above always takes
    priority when entries exist). Grounds its response only in real,
    already-collected Business DNA facts -- service description,
    fulfillment type, booking availability -- and deliberately never sees a
    price or numeric fact in its context, so there is nothing for it to
    restate or get wrong. The same _safe_message screen used everywhere
    else in this file is still the backstop against a slip (an invented
    discount, guarantee, or commitment)."""

    def __init__(self, provider: StructuredAIProvider) -> None:
        self.provider = provider

    def generate(
        self,
        objection_phrase: str,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        service_id: str | None = None,
        customer_tone: CustomerTone = CustomerTone.NEUTRAL,
    ) -> CustomerResponse:
        _require_permissions(business_dna, "draft_message")
        communication = _communication(business_dna)
        business = business_dna.get("business", {})
        prompt = universal_reassurance_prompt(
            context={
                "objection_phrase": objection_phrase,
                "language": communication.get("language", "English"),
                "tone": communication.get("tone"),
                "customer_tone": customer_tone.value,
                "channel": channel,
                "business": {
                    "industry": business.get("industry") if isinstance(business, Mapping) else None,
                    "description": business.get("description") if isinstance(business, Mapping) else None,
                },
                "service": self._service_context(business_dna, service_id),
            },
            customer_message=objection_phrase,
        )
        request = AIRequest(
            prompt.identifier,
            prompt.version,
            "universal_reassurance_response_generation",
            prompt.system,
            prompt.user,
            UniversalReassuranceOutput,
        )
        result = self.provider.generate(request)
        if not _safe_message(result.output.message_text, business_dna):
            raise AIInvalidOutputError(
                "AI universal reassurance response made an unsafe commitment",
                metadata=_invalid_metadata(result.metadata),
            )
        return CustomerResponse(
            result.output.message_text.strip(),
            channel,
            "objection_reassurance",
            case_id,
            ai_metadata=_audit(result.metadata),
        )

    @staticmethod
    def _service_context(
        business_dna: Mapping[str, object], service_id: str | None
    ) -> Mapping[str, object] | None:
        if not service_id:
            return None
        services = business_dna.get("services", [])
        if not isinstance(services, list):
            return None
        for service in services:
            if isinstance(service, Mapping) and service.get("id") == service_id:
                # Deliberately no price/amount field here -- objection
                # reassurance must never state a number the customer could
                # hold the business to. fulfillment_type alone conveys the
                # true structural fact (e.g. quote_required means a quote
                # step necessarily precedes any payment).
                return {
                    "description": service.get("description"),
                    "fulfillment_type": service.get("fulfillment_type"),
                    "booking_allowed": service.get("booking_allowed"),
                }
        return None
