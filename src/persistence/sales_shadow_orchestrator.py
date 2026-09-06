"""Fail-open orchestration for post-response sales shadow generation."""

from datetime import datetime

from src.ai.errors import AIInvalidOutputError, AIProviderError
from src.ai.sales_response_generator import AISalesResponseGenerator, SalesResponseGenerationInput
from src.domain.sales import SalesShadowResult, SalesShadowStatus
from src.engine.sales_response_validator import SalesResponseValidationContext

from .sales_shadow_service import SalesShadowIdentity, SalesShadowService


class SalesShadowOrchestrator:
    """Generate and persist a comparison result; never deliver it to a customer."""

    def __init__(self, generator: AISalesResponseGenerator, service: SalesShadowService) -> None:
        self._generator = generator
        self._service = service

    def run(
        self, identity: SalesShadowIdentity, generation_input: SalesResponseGenerationInput, *,
        validation_context: SalesResponseValidationContext,
        delivered_response_text: str | None, now: datetime,
        persist_provider_errors: bool = True,
    ) -> SalesShadowResult:
        try:
            generated = self._generator.generate(generation_input)
        except AIInvalidOutputError as exc:
            return self._service.record_error(
                identity, approved_move=validation_context.approved_move,
                status=SalesShadowStatus.VALIDATOR_ERROR,
                violation="provider output did not match SalesResponseOutput",
                delivered_response_text=delivered_response_text,
                model_name=exc.metadata.model if exc.metadata else None, now=now,
            )
        except AIProviderError as exc:
            if not persist_provider_errors:
                raise
            return self._service.record_error(
                identity, approved_move=validation_context.approved_move,
                status=SalesShadowStatus.PROVIDER_ERROR,
                violation=f"AI provider failure: {exc.category}",
                delivered_response_text=delivered_response_text,
                model_name=exc.metadata.model if exc.metadata else None, now=now,
            )
        return self._service.record_candidate(
            identity, generated.output, context=validation_context,
            delivered_response_text=delivered_response_text,
            model_name=generated.metadata.model, now=now,
        )
