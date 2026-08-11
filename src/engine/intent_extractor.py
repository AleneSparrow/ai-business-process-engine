"""Provider-neutral intent extraction boundary."""

import re
from typing import Mapping, Protocol

from src.domain.qualification import IncomingMessage, IntentResult, Urgency


class IntentExtractor(Protocol):
    def extract(self, message: IncomingMessage, business_dna: Mapping[str, object]) -> IntentResult: ...


class DeterministicIntentExtractor:
    """Scriptable extractor for tests and local demos; never calls an external model."""

    def __init__(self, scripted_results: Mapping[str, IntentResult] | None = None) -> None:
        self._scripted_results = dict(scripted_results or {})

    def extract(self, message: IncomingMessage, business_dna: Mapping[str, object]) -> IntentResult:
        scripted = self._scripted_results.get(message.external_message_id)
        if scripted is not None:
            return scripted

        text = message.raw_text.casefold()
        services = business_dna.get("services", [])
        matches: list[str] = []
        if isinstance(services, list):
            for service in services:
                if not isinstance(service, Mapping):
                    continue
                terms = [service.get("id"), service.get("name"), *service.get("intake_keywords", [])]
                if any(isinstance(term, str) and term.casefold() in text for term in terms):
                    service_id = service.get("id")
                    if isinstance(service_id, str):
                        matches.append(service_id)

        postal_match = re.search(r"\b\d{5}(?:-\d{4})?\b", message.raw_text)
        urgency = Urgency.NORMAL
        if any(term in text for term in ("emergency", "urgent", "asap")):
            urgency = Urgency.EMERGENCY if "emergency" in text else Urgency.HIGH

        unique_matches = tuple(dict.fromkeys(matches))
        ambiguous = len(unique_matches) > 1
        return IntentResult(
            service_requested=unique_matches[0] if len(unique_matches) == 1 else None,
            urgency=urgency,
            customer_location=postal_match.group(0) if postal_match else None,
            notes=message.raw_text,
            confidence=0.4 if ambiguous else (0.95 if unique_matches else 0.6),
            requires_human=ambiguous,
        )
