"""Provider-neutral intent extraction boundary."""

import re
from typing import Mapping, Protocol

from src.domain.qualification import IncomingMessage, IntentResult, Urgency


class IntentExtractor(Protocol):
    def extract(self, message: IncomingMessage, business_dna: Mapping[str, object]) -> IntentResult: ...


# One word of a person's name: letters, apostrophes and hyphens, but never a
# word that plainly begins the next clause. Without this guard "My name is Ada
# and my phone is ..." captures "Ada and my phone is".
_NAME_STOP = r"(?!(?:and|my|phone|number|email|call|text|but|so|please)\b)"
_NAME_TOKEN = _NAME_STOP + r"[A-Za-z][A-Za-z'-]*"


class DeterministicIntentExtractor:
    """Scriptable extractor for tests and local demos; never calls an external model."""

    def __init__(self, scripted_results: Mapping[str, IntentResult] | None = None) -> None:
        self._scripted_results = dict(scripted_results or {})

    def extract(self, message: IncomingMessage, business_dna: Mapping[str, object]) -> IntentResult:
        scripted = self._scripted_results.get(message.external_message_id)
        if scripted is not None:
            return scripted

        raw_text = message.raw_text.strip()
        text = raw_text.casefold()
        services = business_dna.get("services", [])
        matches: list[str] = []
        if isinstance(services, list):
            for service in services:
                if not isinstance(service, Mapping):
                    continue
                terms = [service.get("id"), service.get("name"), *service.get("intake_keywords", [])]
                if any(
                    isinstance(term, str)
                    and re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", raw_text, re.IGNORECASE)
                    for term in terms
                    if isinstance(term, str) and term.strip()
                ):
                    service_id = service.get("id")
                    if isinstance(service_id, str):
                        matches.append(service_id)

        postal_match = re.search(r"\b\d{5}(?:-\d{4})?\b", message.raw_text)
        email_match = re.search(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b", raw_text)
        phone_candidates = tuple(re.finditer(
            r"(?<!\w)(?:\+?\d[\d .()\-]{5,}\d)(?!\w)", raw_text
        ))
        unique_matches = tuple(dict.fromkeys(matches))
        context = message.conversation_context
        unresolved = set(context.unresolved_items) if context is not None else set()
        phone_context = "field:phone" in unresolved or bool(re.search(
            r"\b(?:phone|call|text|reach|number)\b", raw_text, re.IGNORECASE
        ))
        phone = next((
            candidate.group(0).strip()
            for candidate in phone_candidates
            if 7 <= len(re.sub(r"\D", "", candidate.group(0))) <= 15
            and (
                candidate.group(0).lstrip().startswith("+")
                or phone_context
                or len(re.sub(r"\D", "", candidate.group(0))) >= 10
            )
            and not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", candidate.group(0).strip()
            )
            and len(re.findall(r"\b\d{5}(?:-\d{4})?\b", candidate.group(0))) < 2
        ), None)
        suspicious_instruction = bool(re.search(
            r"\b(?:ignore (?:all |previous |prior )?(?:instructions|rules)|"
            r"system prompt|bypass (?:policy|rules)|mark me qualified)\b",
            raw_text,
            re.IGNORECASE,
        ))
        # The old pattern anchored on $, so the name had to be the last thing
        # in the message: "My name is Ada" worked, "My name is Ada and my
        # phone is 555-0188" returned nothing at all. That is a normal way to
        # write a reply, and dropping the name there is not harmless -- the
        # identity check in PersistentLeadIntakeService needs a name to
        # recognise a returning customer, so a nameless lead whose phone
        # already belongs to someone gets escalated as a contact conflict.
        # Now the name is read as up to four words and stops at a separator
        # or at a word that starts the next clause.
        explicit_name = re.search(
            r"\bmy\s+name\s+is\s+("
            + _NAME_TOKEN + r"(?:\s+" + _NAME_TOKEN + r"){0,3}"
            + r")",
            raw_text,
            re.IGNORECASE,
        )
        customer_name: str | None = (
            explicit_name.group(1).strip(" .,;:!?") if explicit_name else None
        )
        if (
            customer_name is None
            and not suspicious_instruction
            and "field:name" in unresolved
            and len(raw_text.split()) <= 6
        ):
            has_other_answer = bool(postal_match or email_match or phone or unique_matches)
            has_question_answer = any(item.startswith("question:") for item in unresolved)
            if not has_other_answer and not has_question_answer:
                customer_name = raw_text
        answerable_questions = [
            item.removeprefix("question:")
            for item in unresolved
            if item.startswith("question:")
        ]
        answers = (
            {answerable_questions[0]: raw_text}
            if len(answerable_questions) == 1 and raw_text and not suspicious_instruction
            else {}
        )
        urgency = Urgency.NORMAL
        if any(term in text for term in ("emergency", "urgent", "asap")):
            urgency = Urgency.EMERGENCY if "emergency" in text else Urgency.HIGH

        ambiguous = len(unique_matches) > 1
        contextual_answer = context is not None and bool(
            postal_match or email_match or phone or customer_name or answers or unique_matches
        )
        return IntentResult(
            service_requested=unique_matches[0] if len(unique_matches) == 1 else None,
            urgency=urgency,
            customer_location=postal_match.group(0) if postal_match else None,
            notes=message.raw_text,
            confidence=0.4 if ambiguous else (0.95 if unique_matches or contextual_answer else 0.6),
            requires_human=ambiguous,
            qualification_answers=answers,
            customer_name=customer_name,
            phone=phone,
            email=email_match.group(0) if email_match else None,
        )
