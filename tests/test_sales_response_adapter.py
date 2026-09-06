from src.ai.sales_response_adapter import to_sales_response_candidate
from src.ai.sales_response_models import SalesResponseOutput
from src.domain.sales import SalesMove


def test_adapter_copies_only_validation_contract_fields() -> None:
    output = SalesResponseOutput(
        move=SalesMove.ASK_DISCOVERY_QUESTION,
        message_text="What outcome matters most?",
        knowledge_ids=[],
        business_fact_ids=["fact-1"],
        customer_evidence_ids=["evidence-1"],
        used_safe_fallback=False,
    )

    candidate = to_sales_response_candidate(output)

    assert candidate.move is SalesMove.ASK_DISCOVERY_QUESTION
    assert candidate.message_text == "What outcome matters most?"
    assert candidate.business_fact_ids == ("fact-1",)
    assert candidate.customer_evidence_ids == ("evidence-1",)
