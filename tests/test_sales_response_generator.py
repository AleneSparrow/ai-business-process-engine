from src.ai.fake_provider import FakeAIProvider
from src.ai.sales_response_generator import AISalesResponseGenerator, SalesResponseGenerationInput
from src.ai.sales_response_models import SalesResponseOutput
from src.domain.sales import SalesMove, SalesStage


def test_generator_uses_structured_sales_contract_without_delivery_capability() -> None:
    provider = FakeAIProvider([SalesResponseOutput(
        move=SalesMove.ASK_DISCOVERY_QUESTION,
        message_text="What result matters most?",
    )])
    generator = AISalesResponseGenerator(provider)

    result = generator.generate(SalesResponseGenerationInput(
        approved_move=SalesMove.ASK_DISCOVERY_QUESTION,
        sales_stage=SalesStage.DISCOVERY,
        channel="webchat",
        customer_tone="neutral",
        knowledge_cards=(), business_facts=(), customer_evidence=(),
        handoff_template=None, safe_fallback_text="I can ask the team to help.",
        conversation_context={}, customer_message="Tell me more.",
    ))

    assert result.output.message_text == "What result matters most?"
    request = provider.requests[0]
    assert request.output_model is SalesResponseOutput
    assert request.decision_type == "sales_response_generation"
