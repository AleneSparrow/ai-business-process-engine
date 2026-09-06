"""Validated, candidate-only ingestion for owner-reviewed sales knowledge."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.exc import IntegrityError

from src.domain.sales import SalesKnowledgeCard, SalesKnowledgeStatus
from src.domain.models import _require_aware, _require_text

from .repositories import UnitOfWork


@dataclass(frozen=True, slots=True)
class SalesKnowledgeImportItem:
    knowledge_id: str
    version: int
    source: Mapping[str, Any]
    principle: str
    applicable_when: tuple[str, ...]
    prohibited_when: tuple[str, ...] = ()
    required_sequence: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    approved_examples: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SalesKnowledgeImportCheck:
    knowledge_id: str
    version: int
    status: str


@dataclass(frozen=True, slots=True)
class SalesKnowledgeImportResult:
    valid: bool
    imported: bool
    checks: tuple[SalesKnowledgeImportCheck, ...]


class SalesKnowledgeImportService:
    """Imports a batch atomically, always as CANDIDATE and never as approved."""

    def __init__(self, unit_of_work_factory) -> None:
        self.unit_of_work_factory = unit_of_work_factory

    def validate(
        self, business_id: str, items: tuple[SalesKnowledgeImportItem, ...]
    ) -> SalesKnowledgeImportResult:
        _require_text(business_id, "business_id")
        if not items:
            raise ValueError("at least one knowledge card is required")
        identities = [(item.knowledge_id, item.version) for item in items]
        if len(set(identities)) != len(identities):
            raise ValueError("knowledge_id and version must be unique within an import")
        with self.unit_of_work_factory() as uow:
            checks = tuple(
                SalesKnowledgeImportCheck(
                    item.knowledge_id,
                    item.version,
                    "DUPLICATE_VERSION"
                    if uow.sales_knowledge.get(business_id, item.knowledge_id, item.version)
                    else "READY",
                )
                for item in items
            )
        return SalesKnowledgeImportResult(
            valid=all(check.status == "READY" for check in checks),
            imported=False,
            checks=checks,
        )

    def import_candidates(
        self,
        business_id: str,
        items: tuple[SalesKnowledgeImportItem, ...],
        *,
        now: datetime,
    ) -> SalesKnowledgeImportResult:
        _require_aware(now, "now")
        result = self.validate(business_id, items)
        if not result.valid:
            return result
        cards = tuple(self._to_candidate(business_id, item, now) for item in items)
        try:
            with self.unit_of_work_factory() as uow:
                # Recheck inside the write transaction. The PK remains the final race-safe guard.
                if any(
                    uow.sales_knowledge.get(business_id, card.knowledge_id, card.version)
                    for card in cards
                ):
                    return self.validate(business_id, items)
                for card in cards:
                    uow.sales_knowledge.add(card, now=now)
                uow.commit()
        except IntegrityError:
            # A concurrent importer won after our check. Expose the same safe conflict result.
            conflict = self.validate(business_id, items)
            if conflict.valid:
                # Do not mislabel an unrelated database integrity failure as a version race.
                raise
            return conflict
        return SalesKnowledgeImportResult(True, True, result.checks)

    @staticmethod
    def _to_candidate(
        business_id: str, item: SalesKnowledgeImportItem, now: datetime
    ) -> SalesKnowledgeCard:
        return SalesKnowledgeCard(
            knowledge_id=item.knowledge_id,
            business_id=business_id,
            version=item.version,
            status=SalesKnowledgeStatus.CANDIDATE,
            source=item.source,
            principle=item.principle,
            applicable_when=item.applicable_when,
            prohibited_when=item.prohibited_when,
            required_sequence=item.required_sequence,
            forbidden_actions=item.forbidden_actions,
            approved_examples=item.approved_examples,
            created_at=now,
        )
