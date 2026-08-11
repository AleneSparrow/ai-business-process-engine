"""Repository abstractions and SQLAlchemy persistence adapters."""

from .errors import IdempotencyCollisionError, MessageScopeError, StaleCaseError
from .sqlalchemy_uow import SQLAlchemyUnitOfWork
from .lead_intake import PersistentLeadIntakeService
from .repositories import (
    BusinessDNARepository,
    BusinessRepository,
    IdempotencyRepository,
    LeadRepository,
    ProcessCaseRepository,
    ProcessEventRepository,
    UnitOfWork,
)

__all__ = [
    "IdempotencyCollisionError",
    "BusinessDNARepository",
    "BusinessRepository",
    "IdempotencyRepository",
    "LeadRepository",
    "MessageScopeError",
    "PersistentLeadIntakeService",
    "ProcessCaseRepository",
    "ProcessEventRepository",
    "SQLAlchemyUnitOfWork",
    "StaleCaseError",
    "UnitOfWork",
]
