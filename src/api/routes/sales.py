"""Tenant-scoped staff API for governed sales configuration and audit state."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.domain.auth import StaffUser
from src.domain.models import utc_now
from src.domain.sales import SalesKnowledgeStatus, SalesTurnAnalysis
from src.engine.sales_policy import SalesPolicyEngine
from src.persistence.sales_knowledge_import_service import SalesKnowledgeImportService

from ..dependencies import (
    BusinessIdPath,
    UnitOfWorkFactory,
    get_unit_of_work_factory,
    require_own_business,
)
from ..errors import ConflictError, RequestDataError, ResourceNotFoundError
from ..schemas import (
    SalesCaseContextResponse,
    SalesKnowledgeCardListResponse,
    SalesKnowledgeCardSchema,
    SalesKnowledgeImportRequest,
    SalesKnowledgeImportResponse,
    SalesObjectionRecordSchema,
    SalesPlaybookListResponse,
    SalesPlaybookSchema,
    SalesTurnListResponse,
    SalesTurnSchema,
    SalesShadowEvaluationRequest,
    SalesShadowResultListResponse,
    SalesShadowResultSchema,
)


router = APIRouter(prefix="/api/v1/businesses/{business_id}/sales", tags=["sales"])


@router.post("/knowledge-cards/import/validate", response_model=SalesKnowledgeImportResponse)
def validate_knowledge_import(
    business_id: BusinessIdPath,
    body: SalesKnowledgeImportRequest,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesKnowledgeImportResponse:
    try:
        result = SalesKnowledgeImportService(unit_of_work_factory).validate(
            business_id, tuple(card.to_service_item() for card in body.cards)
        )
    except ValueError as exc:
        raise RequestDataError(str(exc)) from exc
    return SalesKnowledgeImportResponse.from_result(result)


@router.post("/knowledge-cards/import", response_model=SalesKnowledgeImportResponse)
def import_knowledge_candidates(
    business_id: BusinessIdPath,
    body: SalesKnowledgeImportRequest,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesKnowledgeImportResponse:
    try:
        result = SalesKnowledgeImportService(unit_of_work_factory).import_candidates(
            business_id,
            tuple(card.to_service_item() for card in body.cards),
            now=utc_now(),
        )
    except ValueError as exc:
        raise RequestDataError(str(exc)) from exc
    if not result.valid:
        raise ConflictError(
            "sales_knowledge_version_conflict",
            "One or more knowledge card versions already exist",
        )
    return SalesKnowledgeImportResponse.from_result(result)


@router.get("/playbook", response_model=SalesPlaybookSchema)
def get_active_playbook(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesPlaybookSchema:
    with unit_of_work_factory() as unit_of_work:
        playbook = unit_of_work.sales_playbooks.get_active(business_id)
    if playbook is None:
        raise ResourceNotFoundError("sales_playbook_not_found", "No published sales playbook was found")
    return SalesPlaybookSchema.from_domain(playbook)


@router.get("/playbooks", response_model=SalesPlaybookListResponse)
def list_playbooks(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesPlaybookListResponse:
    with unit_of_work_factory() as unit_of_work:
        values = unit_of_work.sales_playbooks.list_versions(business_id)
    return SalesPlaybookListResponse(
        playbooks=tuple(SalesPlaybookSchema.from_domain(value) for value in values)
    )


@router.get("/knowledge-cards", response_model=SalesKnowledgeCardListResponse)
def list_knowledge_cards(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
    card_status: Annotated[SalesKnowledgeStatus | None, Query(alias="status")] = None,
) -> SalesKnowledgeCardListResponse:
    with unit_of_work_factory() as unit_of_work:
        values = unit_of_work.sales_knowledge.list_for_business(
            business_id, status=card_status
        )
    return SalesKnowledgeCardListResponse(
        cards=tuple(SalesKnowledgeCardSchema.from_domain(value) for value in values)
    )


def _review_card(
    business_id: str,
    knowledge_id: str,
    version: int,
    status: SalesKnowledgeStatus,
    reviewed_by: str,
    unit_of_work_factory: UnitOfWorkFactory,
) -> SalesKnowledgeCardSchema:
    with unit_of_work_factory() as unit_of_work:
        existing = unit_of_work.sales_knowledge.get(business_id, knowledge_id, version)
        if existing is None:
            raise ResourceNotFoundError("sales_knowledge_not_found", "Sales knowledge card was not found")
        updated = unit_of_work.sales_knowledge.set_status(
            business_id, knowledge_id, version, status=status,
            reviewed_at=utc_now(), reviewed_by=reviewed_by,
        )
        if updated is None:
            raise ConflictError(
                "sales_knowledge_already_reviewed",
                "Only a candidate sales knowledge card can be reviewed",
            )
        unit_of_work.commit()
    return SalesKnowledgeCardSchema.from_domain(updated)


@router.post("/knowledge-cards/{knowledge_id}/versions/{version}/approve", response_model=SalesKnowledgeCardSchema)
def approve_knowledge_card(
    business_id: BusinessIdPath,
    knowledge_id: str,
    version: int,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesKnowledgeCardSchema:
    return _review_card(
        business_id, knowledge_id, version, SalesKnowledgeStatus.APPROVED,
        user.user_id, unit_of_work_factory
    )


@router.post("/knowledge-cards/{knowledge_id}/versions/{version}/reject", response_model=SalesKnowledgeCardSchema)
def reject_knowledge_card(
    business_id: BusinessIdPath,
    knowledge_id: str,
    version: int,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesKnowledgeCardSchema:
    return _review_card(
        business_id, knowledge_id, version, SalesKnowledgeStatus.REJECTED,
        user.user_id, unit_of_work_factory
    )


@router.get("/cases/{case_id}", response_model=SalesCaseContextResponse)
def get_case_sales_context(
    business_id: BusinessIdPath,
    case_id: str,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesCaseContextResponse:
    with unit_of_work_factory() as unit_of_work:
        case = unit_of_work.cases.get(business_id, case_id)
        if case is None:
            raise ResourceNotFoundError("case_not_found", "Case was not found")
        profile = unit_of_work.sales_profiles.get(business_id, case_id)
        if profile is None:
            raise ResourceNotFoundError("sales_profile_not_found", "Sales profile was not found")
        objections = unit_of_work.sales_objections.list_for_case(business_id, case_id)
        approved_knowledge_available = bool(unit_of_work.sales_knowledge.list_approved(business_id))

    preview = SalesPolicyEngine().decide(
        profile,
        SalesTurnAnalysis(
            observed_stage=profile.stage,
            confidence=1.0,
            objections=(() if profile.active_objection is None else (profile.active_objection,)),
            commitment_level=profile.commitment_level,
            requested_callback_at=profile.preferred_contact_at,
        ),
        approved_knowledge_available=approved_knowledge_available,
        booking_available=False,
    )
    return SalesCaseContextResponse(
        case_id=case_id,
        stage=profile.stage,
        customer_goal=profile.customer_goal,
        current_problem=profile.current_problem,
        desired_outcome=profile.desired_outcome,
        decision_criteria=profile.decision_criteria,
        commitment_level=profile.commitment_level.value,
        preferred_channel=profile.preferred_channel,
        preferred_contact_at=profile.preferred_contact_at,
        last_move=profile.last_move,
        next_approved_action=preview.move,
        next_action_reason=preview.reason_code,
        requires_human=preview.requires_human,
        human_review_reason=preview.reason_code if preview.requires_human else None,
        version=profile.version,
        objections=tuple(SalesObjectionRecordSchema.from_domain(value) for value in objections),
    )


@router.get("/cases/{case_id}/turns", response_model=SalesTurnListResponse)
def list_case_sales_turns(
    business_id: BusinessIdPath,
    case_id: str,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesTurnListResponse:
    with unit_of_work_factory() as unit_of_work:
        if unit_of_work.cases.get(business_id, case_id) is None:
            raise ResourceNotFoundError("case_not_found", "Case was not found")
        turns = unit_of_work.sales_turns.list_for_case(business_id, case_id)
    return SalesTurnListResponse(turns=tuple(SalesTurnSchema.from_domain(value) for value in turns))


@router.get("/cases/{case_id}/shadow-results", response_model=SalesShadowResultListResponse)
def list_case_shadow_results(
    business_id: BusinessIdPath,
    case_id: str,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesShadowResultListResponse:
    with unit_of_work_factory() as unit_of_work:
        if unit_of_work.cases.get(business_id, case_id) is None:
            raise ResourceNotFoundError("case_not_found", "Case was not found")
        values = unit_of_work.sales_shadow_results.list_for_case(business_id, case_id)
    return SalesShadowResultListResponse(
        results=tuple(SalesShadowResultSchema.from_domain(value) for value in values)
    )


@router.post(
    "/cases/{case_id}/shadow-results/{shadow_id}/evaluate",
    response_model=SalesShadowResultSchema,
)
def evaluate_shadow_result(
    business_id: BusinessIdPath,
    case_id: str,
    shadow_id: str,
    body: SalesShadowEvaluationRequest,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> SalesShadowResultSchema:
    with unit_of_work_factory() as unit_of_work:
        existing = unit_of_work.sales_shadow_results.get(business_id, case_id, shadow_id)
        if existing is None:
            raise ResourceNotFoundError("sales_shadow_not_found", "Sales shadow result was not found")
        updated = unit_of_work.sales_shadow_results.evaluate(
            business_id, case_id, shadow_id, evaluation=body.evaluation,
            evaluated_by=user.user_id, evaluated_at=utc_now(),
        )
        if updated is None:
            raise ConflictError(
                "sales_shadow_already_evaluated", "Sales shadow result can only be evaluated once"
            )
        unit_of_work.commit()
    return SalesShadowResultSchema.from_domain(updated)
