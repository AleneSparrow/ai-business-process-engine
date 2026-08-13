"""Staff-facing dashboard API: real cases, conversations, audit trail, and
the reply/resolve actions for a case that needs a human (Milestone 8 slice 2
and its follow-up). Every endpoint is scoped to the authenticated staff
user's own business via `require_own_business` — no cross-tenant reads or
actions are possible even with a valid session token for a different
business.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.domain.auth import StaffUser
from src.persistence.staff_action_service import StaffActionService

from ..dependencies import (
    BusinessIdPath,
    UnitOfWorkFactory,
    get_staff_action_service,
    get_unit_of_work_factory,
    require_active_subscription,
    require_own_business,
)
from ..errors import ResourceNotFoundError
from ..schemas import (
    DashboardCaseDetailResponse,
    DashboardCaseListResponse,
    DashboardCaseSummarySchema,
    DashboardConversationDetailResponse,
    DashboardConversationListResponse,
    DashboardConversationSchema,
    DashboardMessageSchema,
    StaffActionResponse,
    StaffReplyRequest,
)


# Gated on require_active_subscription: this is the actual delivered product
# (cases and conversations), so it's what's blocked when a business's own
# Atelier subscription lapses. Settings, billing itself, and public lead
# intake stay reachable regardless -- see src/api/dependencies.py.
router = APIRouter(
    prefix="/api/v1/businesses/{business_id}",
    tags=["dashboard"],
    dependencies=[Depends(require_active_subscription)],
)


@router.get("/cases", response_model=DashboardCaseListResponse)
def list_cases(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> DashboardCaseListResponse:
    with unit_of_work_factory() as unit_of_work:
        cases = unit_of_work.cases.list_for_business(business_id)
    return DashboardCaseListResponse(
        cases=tuple(DashboardCaseSummarySchema.from_domain(case) for case in cases)
    )


@router.get("/cases/{case_id}", response_model=DashboardCaseDetailResponse)
def get_case(
    business_id: BusinessIdPath,
    case_id: str,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> DashboardCaseDetailResponse:
    with unit_of_work_factory() as unit_of_work:
        case = unit_of_work.cases.get(business_id, case_id)
        if case is None:
            raise ResourceNotFoundError("case_not_found", "Case was not found")
    return DashboardCaseDetailResponse.from_domain(case)


@router.get("/conversations", response_model=DashboardConversationListResponse)
def list_conversations(
    business_id: BusinessIdPath,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> DashboardConversationListResponse:
    with unit_of_work_factory() as unit_of_work:
        conversations = unit_of_work.conversations.list_for_business(business_id)
        schemas = []
        for conversation in conversations:
            lead_name = None
            if conversation.lead_id is not None:
                lead = unit_of_work.leads.get(business_id, conversation.lead_id)
                lead_name = lead.name if lead is not None else None
            case_state = None
            if conversation.case_id is not None:
                case = unit_of_work.cases.get(business_id, conversation.case_id)
                case_state = case.current_state if case is not None else None
            schemas.append(
                DashboardConversationSchema.from_domain(
                    conversation, lead_name=lead_name, case_state=case_state
                )
            )
    return DashboardConversationListResponse(conversations=tuple(schemas))


@router.get("/conversations/{conversation_id}", response_model=DashboardConversationDetailResponse)
def get_conversation(
    business_id: BusinessIdPath,
    conversation_id: str,
    user: Annotated[StaffUser, Depends(require_own_business)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> DashboardConversationDetailResponse:
    with unit_of_work_factory() as unit_of_work:
        conversation = unit_of_work.conversations.get(business_id, conversation_id)
        if conversation is None:
            raise ResourceNotFoundError("conversation_not_found", "Conversation was not found")
        lead_name = None
        if conversation.lead_id is not None:
            lead = unit_of_work.leads.get(business_id, conversation.lead_id)
            lead_name = lead.name if lead is not None else None
        case_state = None
        if conversation.case_id is not None:
            case = unit_of_work.cases.get(business_id, conversation.case_id)
            case_state = case.current_state if case is not None else None
        messages = unit_of_work.conversation_messages.list_for_conversation(business_id, conversation_id)
    return DashboardConversationDetailResponse(
        conversation=DashboardConversationSchema.from_domain(
            conversation, lead_name=lead_name, case_state=case_state
        ),
        messages=tuple(
            DashboardMessageSchema(
                message_id=message.message_id,
                direction=message.direction,
                role=message.role,
                text=message.text,
                created_at=message.created_at,
            )
            for message in messages
        ),
    )


def _staff_action_response(
    unit_of_work_factory: UnitOfWorkFactory, business_id: str, result
) -> StaffActionResponse:
    lead_name = None
    with unit_of_work_factory() as unit_of_work:
        if result.conversation.lead_id is not None:
            lead = unit_of_work.leads.get(business_id, result.conversation.lead_id)
            lead_name = lead.name if lead is not None else None
    return StaffActionResponse(
        conversation=DashboardConversationSchema.from_domain(
            result.conversation,
            lead_name=lead_name,
            case_state=result.case.current_state if result.case is not None else None,
        ),
        case=DashboardCaseSummarySchema.from_domain(result.case) if result.case is not None else None,
    )


@router.post(
    "/conversations/{conversation_id}/reply",
    response_model=StaffActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def reply_to_conversation(
    business_id: BusinessIdPath,
    conversation_id: str,
    body: StaffReplyRequest,
    user: Annotated[StaffUser, Depends(require_own_business)],
    staff_actions: Annotated[StaffActionService, Depends(get_staff_action_service)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> StaffActionResponse:
    result = staff_actions.reply(business_id, conversation_id, user, body.message)
    return _staff_action_response(unit_of_work_factory, business_id, result)


@router.post(
    "/conversations/{conversation_id}/resolve",
    response_model=StaffActionResponse,
)
def resolve_conversation_case(
    business_id: BusinessIdPath,
    conversation_id: str,
    user: Annotated[StaffUser, Depends(require_own_business)],
    staff_actions: Annotated[StaffActionService, Depends(get_staff_action_service)],
    unit_of_work_factory: Annotated[UnitOfWorkFactory, Depends(get_unit_of_work_factory)],
) -> StaffActionResponse:
    result = staff_actions.resolve(business_id, conversation_id, user)
    return _staff_action_response(unit_of_work_factory, business_id, result)
