"""Lazy quote/payment expiry as an operator-triggered sweep."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.domain.commercial import PaymentStatus, QuoteStatus

from .commercial_service import CommercialWorkflowService
from .sqlalchemy_models import PaymentRequestRow, QuoteRow

if TYPE_CHECKING:
    from .repositories import UnitOfWorkFactory


class CommercialExpirySweep:
    def __init__(self, unit_of_work_factory: "UnitOfWorkFactory") -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.commercial = CommercialWorkflowService()

    def run(self, now: datetime, *, limit: int = 200) -> dict[str, int]:
        with self.unit_of_work_factory() as uow:
            session = getattr(uow, "session", None)
            if session is None:
                return {"cases_scanned": 0}
            quote_pairs = session.execute(
                select(QuoteRow.business_id, QuoteRow.case_id)
                .where(
                    QuoteRow.status == QuoteStatus.PRESENTED.value,
                    QuoteRow.valid_until <= now,
                )
                .limit(limit)
            ).all()
            payment_pairs = session.execute(
                select(PaymentRequestRow.business_id, PaymentRequestRow.case_id)
                .where(
                    PaymentRequestRow.status.in_(
                        [
                            PaymentStatus.PENDING.value,
                            PaymentStatus.READY.value,
                            PaymentStatus.FAILED.value,
                        ]
                    ),
                    PaymentRequestRow.expires_at <= now,
                )
                .limit(limit)
            ).all()
        targets = list(dict.fromkeys([*quote_pairs, *payment_pairs]))
        scanned = 0
        for business_id, case_id in targets:
            with self.unit_of_work_factory() as uow:
                case = uow.cases.get(business_id, case_id)
                if case is None:
                    continue
                self.commercial.expire_due_items(uow, case, occurred_at=now)
                uow.commit()
                scanned += 1
        return {"cases_scanned": scanned}
