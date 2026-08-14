"""Customer-response wording boundary; decisions remain outside this module."""

from typing import Mapping, Protocol

from src.domain.qualification import CustomerResponse


class CustomerResponseGenerator(Protocol):
    def generate(
        self,
        *,
        response_type: str,
        approved_message: str,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        requires_human: bool,
    ) -> CustomerResponse: ...


class DeterministicCustomerResponseGenerator:
    """Returns the Business-DNA-approved wording, plus any business-configured
    compliance disclaimer appended deterministically here in code -- never
    left to the AI to remember or to a prompt instruction it could drop. See
    `communication.compliance_disclaimer` in the Business DNA schema."""

    def generate(
        self,
        *,
        response_type: str,
        approved_message: str,
        business_dna: Mapping[str, object],
        channel: str,
        case_id: str,
        requires_human: bool,
    ) -> CustomerResponse:
        return CustomerResponse(
            _with_compliance_disclaimer(approved_message, business_dna),
            channel,
            response_type,
            case_id,
            requires_human,
        )


def _with_compliance_disclaimer(message: str, business_dna: Mapping[str, object]) -> str:
    communication = business_dna.get("communication") if isinstance(business_dna, Mapping) else None
    disclaimer = communication.get("compliance_disclaimer") if isinstance(communication, Mapping) else None
    if not isinstance(disclaimer, str):
        return message
    disclaimer = disclaimer.strip()
    if not disclaimer or disclaimer in message:
        return message
    return f"{message}\n\n{disclaimer}"
