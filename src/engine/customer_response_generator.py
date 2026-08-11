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
    """Returns the Business-DNA-approved wording unchanged."""

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
        del business_dna
        return CustomerResponse(
            approved_message,
            channel,
            response_type,
            case_id,
            requires_human,
        )
