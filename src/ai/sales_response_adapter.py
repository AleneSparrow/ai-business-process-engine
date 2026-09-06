"""Narrow production boundary for experimental sales response output."""

from src.ai.sales_response_models import SalesResponseOutput
from src.engine.sales_response_validator import SalesResponseCandidate


def to_sales_response_candidate(output: SalesResponseOutput) -> SalesResponseCandidate:
    """Copy only declared, provider-neutral fields into the policy validator."""
    return SalesResponseCandidate(
        message_text=output.message_text,
        move=output.move,
        knowledge_ids=tuple(output.knowledge_ids),
        business_fact_ids=tuple(output.business_fact_ids),
        customer_evidence_ids=tuple(output.customer_evidence_ids),
        used_safe_fallback=output.used_safe_fallback,
    )
