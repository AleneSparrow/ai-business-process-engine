from datetime import datetime, timezone

from src.ai.errors import AIInvalidOutputError, AITransportError
from src.domain.sales import SalesMove, SalesShadowStatus
from src.persistence.sales_shadow_orchestrator import SalesShadowOrchestrator
from src.persistence.sales_shadow_service import SalesShadowIdentity


class FailingGenerator:
    def __init__(self, error): self.error = error
    def generate(self, value): raise self.error


class RecordingService:
    def __init__(self): self.error = None
    def record_error(self, identity, **kwargs):
        self.error = kwargs
        return kwargs


def _run(error):
    from src.ai.sales_response_generator import SalesResponseGenerationInput
    from src.domain.sales import SalesStage
    from src.engine.sales_response_validator import SalesResponseValidationContext

    service = RecordingService()
    orchestrator = SalesShadowOrchestrator(FailingGenerator(error), service)  # type: ignore[arg-type]
    move = SalesMove.ASK_DISCOVERY_QUESTION
    orchestrator.run(
        SalesShadowIdentity("b", "c", "conversation", "message"),
        SalesResponseGenerationInput(move, SalesStage.DISCOVERY, "webchat", "neutral", (), (), (),
                                     None, "Safe response", {}, "Hello"),
        validation_context=SalesResponseValidationContext(
            approved_move=move, approved_knowledge=frozenset(), approved_business_facts={},
            customer_evidence={}, safe_fallback="Safe response",
        ),
        delivered_response_text="Live response", now=datetime.now(timezone.utc),
    )
    return service.error


def test_invalid_structured_output_becomes_validator_error() -> None:
    recorded = _run(AIInvalidOutputError("invalid"))
    assert recorded["status"] is SalesShadowStatus.VALIDATOR_ERROR


def test_transport_failure_becomes_provider_error_without_customer_delivery() -> None:
    recorded = _run(AITransportError("offline"))
    assert recorded["status"] is SalesShadowStatus.PROVIDER_ERROR
    assert recorded["delivered_response_text"] == "Live response"
