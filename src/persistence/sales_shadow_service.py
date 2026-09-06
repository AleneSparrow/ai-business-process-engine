"""Persist policy-validated comparison responses without delivering them."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from src.ai.sales_response_models import SALES_RESPONSE_PROMPT_VERSION, SalesResponseOutput
from src.ai.sales_response_adapter import to_sales_response_candidate
from src.domain.sales import SalesMove, SalesShadowResult, SalesShadowStatus
from src.engine.sales_response_validator import SalesPolicyValidator, SalesResponseValidationContext
from src.persistence.repositories import UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class SalesShadowIdentity:
    business_id: str
    case_id: str
    conversation_id: str
    source_message_id: str


class SalesShadowService:
    """Records comparison data only; this class has no message-delivery dependency."""

    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def record_candidate(
        self, identity: SalesShadowIdentity, output: SalesResponseOutput, *,
        context: SalesResponseValidationContext, delivered_response_text: str | None,
        model_name: str | None, now: datetime,
    ) -> SalesShadowResult:
        validation = SalesPolicyValidator().validate(to_sales_response_candidate(output), context)
        result = SalesShadowResult(
            shadow_id=str(uuid4()), business_id=identity.business_id, case_id=identity.case_id,
            conversation_id=identity.conversation_id, source_message_id=identity.source_message_id,
            approved_move=context.approved_move,
            status=SalesShadowStatus.VALID if validation.valid else SalesShadowStatus.BLOCKED,
            proposed_response_text=output.message_text,
            delivered_response_text=delivered_response_text,
            knowledge_ids=tuple(output.knowledge_ids), business_fact_ids=tuple(output.business_fact_ids),
            customer_evidence_ids=tuple(output.customer_evidence_ids),
            violations=validation.violations, prompt_version=SALES_RESPONSE_PROMPT_VERSION,
            model_name=model_name, created_at=now,
        )
        return self._persist_once(result)

    def record_error(
        self, identity: SalesShadowIdentity, *, approved_move: SalesMove,
        status: SalesShadowStatus, violation: str, delivered_response_text: str | None,
        model_name: str | None, now: datetime,
    ) -> SalesShadowResult:
        if status not in {SalesShadowStatus.PROVIDER_ERROR, SalesShadowStatus.VALIDATOR_ERROR}:
            raise ValueError("error result requires PROVIDER_ERROR or VALIDATOR_ERROR status")
        result = SalesShadowResult(
            shadow_id=str(uuid4()), business_id=identity.business_id, case_id=identity.case_id,
            conversation_id=identity.conversation_id, source_message_id=identity.source_message_id,
            approved_move=approved_move, status=status, proposed_response_text=None,
            delivered_response_text=delivered_response_text, knowledge_ids=(), business_fact_ids=(),
            customer_evidence_ids=(), violations=(violation,),
            prompt_version=SALES_RESPONSE_PROMPT_VERSION, model_name=model_name, created_at=now,
        )
        return self._persist_once(result)

    def _persist_once(self, result: SalesShadowResult) -> SalesShadowResult:
        with self._unit_of_work_factory() as unit_of_work:
            existing = unit_of_work.sales_shadow_results.list_for_case(result.business_id, result.case_id)
            for value in existing:
                if value.source_message_id == result.source_message_id:
                    return value
            unit_of_work.sales_shadow_results.add(result)
            unit_of_work.commit()
        return result
