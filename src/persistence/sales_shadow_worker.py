"""Lease-based worker for durable post-response sales shadow jobs."""

import logging
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from src.ai.errors import AIInvalidOutputError, AIProviderError
from src.ai.sales_response_generator import SalesResponseGenerationInput
from src.ai.sales_turn_analyzer import AISalesTurnAnalyzer
from src.domain.conversations import ConversationStatus
from src.domain.sales import (
    CustomerSalesProfile, SalesMove, SalesShadowJob, SalesShadowStatus,
    SalesStage, SalesTurn,
)
from src.engine.sales_policy import SalesPolicyEngine
from src.engine.sales_response_validator import SalesResponseValidationContext
from src.persistence.repositories import UnitOfWorkFactory
from .sales_shadow_orchestrator import SalesShadowOrchestrator
from .sales_shadow_service import SalesShadowIdentity

LOGGER = logging.getLogger(__name__)
_STOP = frozenset({"stop", "stopall", "unsubscribe", "cancel", "end", "quit"})


class SalesShadowWorker:
    LEASE = timedelta(minutes=5)

    def __init__(self, unit_of_work_factory: UnitOfWorkFactory,
                 analyzer: AISalesTurnAnalyzer | None,
                 orchestrator: SalesShadowOrchestrator | None,
                 *, worker_id: str | None = None) -> None:
        self._uow_factory = unit_of_work_factory
        self._analyzer = analyzer
        self._orchestrator = orchestrator
        self._worker_id = worker_id or f"shadow-{uuid4()}"

    def run_one(self, *, now: datetime) -> bool:
        with self._uow_factory() as uow:
            job = uow.sales_shadow_jobs.claim_next(
                now=now, lease_owner=self._worker_id, lease_expires_at=now + self.LEASE)
            if job is None:
                return False
            uow.commit()
        try:
            self._process(job, now=now)
        except (AIProviderError, AIInvalidOutputError) as exc:
            self._retry(job, exc.category, now)
        except ControlledShadowFailure as exc:
            self._retry(job, exc.category, now)
        except Exception:
            LOGGER.exception("sales_shadow_job_unexpected business_id=%s job_id=%s",
                             job.business_id, job.job_id)
            self._retry(job, "unexpected_error", now)
        return True

    def _process(self, job: SalesShadowJob, *, now: datetime) -> None:
        with self._uow_factory() as uow:
            conversation = uow.conversations.get(job.business_id, job.conversation_id)
            case = uow.cases.get(job.business_id, job.case_id)
            customer = uow.conversation_messages.get(
                job.business_id, job.conversation_id, job.source_message_id)
            delivered = uow.conversation_messages.get(
                job.business_id, job.conversation_id, job.response_message_id)
            playbook = uow.sales_playbooks.get_active(job.business_id)
            knowledge = uow.sales_knowledge.list_approved(job.business_id)
            profile = uow.sales_profiles.get(job.business_id, job.case_id, for_update=True)
            history = uow.conversation_messages.list_for_conversation(
                job.business_id, job.conversation_id, limit=8)
        if not all((conversation, case, customer, delivered)):
            raise ControlledShadowFailure("missing_job_context")
        assert conversation is not None and customer is not None and delivered is not None
        if conversation.status in {ConversationStatus.HUMAN_TAKEOVER_REQUESTED,
                                    ConversationStatus.HUMAN_TAKEOVER_ACTIVE}:
            self._record_terminal(job, SalesMove.HANDOFF_TO_HUMAN, delivered.text,
                                  "human_takeover_active", now)
            return
        if customer.text.strip().casefold() in _STOP:
            self._record_terminal(job, SalesMove.END_CONTACT, delivered.text,
                                  "contact_not_allowed", now)
            return
        if playbook is None:
            raise ControlledShadowFailure("missing_playbook")
        if self._analyzer is None or self._orchestrator is None:
            raise ControlledShadowFailure("provider_not_configured")

        analyzed = self._analyzer.analyze(
            source_message_id=job.source_message_id, customer_message=customer.text,
            profile_context={} if profile is None else {
                "sales_stage": profile.stage.value,
                "customer_goal": profile.customer_goal,
                "current_problem": profile.current_problem,
                "desired_outcome": profile.desired_outcome,
                "decision_criteria": list(profile.decision_criteria),
                "commitment_level": profile.commitment_level.value,
            },
            conversation_context={"recent_messages": [
                {"role": item.role.value, "text": item.text}
                for item in history if item.message_id != customer.message_id
            ]},
        )
        analysis = analyzed.analysis
        base = profile or CustomerSalesProfile(job.business_id, job.case_id)
        merged = self._merge(base, analysis)
        decision = SalesPolicyEngine().decide(
            merged, analysis, approved_knowledge_available=bool(knowledge),
            booking_available=False)
        evidence = tuple(item.evidence for item in analysis.signals) + tuple(
            item.evidence for item in analysis.objections)
        evidence_map = {f"evidence-{index}": item.excerpt
                        for index, item in enumerate(evidence, start=1)}
        knowledge_map = {card.knowledge_id: card for card in knowledge}
        safe_fallback = ("A team member will follow up with you."
                         if decision.move is SalesMove.HANDOFF_TO_HUMAN
                         else "Thanks for sharing that. A team member can help with the next step.")

        with self._uow_factory() as uow:
            current = uow.sales_profiles.get(job.business_id, job.case_id, for_update=True)
            persisted = replace(merged, stage=decision.target_stage, last_move=decision.move)
            if current is None:
                uow.sales_profiles.add(persisted, now=now)
            else:
                persisted = replace(persisted, version=current.version)
                uow.sales_profiles.save(persisted, current.version, now=now)
            uow.sales_turns.add(SalesTurn(
                turn_id=str(uuid4()), business_id=job.business_id, case_id=job.case_id,
                conversation_id=job.conversation_id, source_message_id=job.source_message_id,
                playbook_version=playbook.version, stage_before=base.stage,
                stage_after=decision.target_stage, move=decision.move,
                reason_code=decision.reason_code, knowledge_ids=tuple(knowledge_map),
                business_fact_ids=(), customer_evidence=evidence,
                analysis={"confidence": analysis.confidence,
                          "recommended_moves": [m.value for m in analysis.recommended_moves]},
                validation={"evidence_grounded": True}, created_at=now))
            uow.commit()

        validation = SalesResponseValidationContext(
            approved_move=decision.move,
            approved_knowledge=frozenset(knowledge_map), approved_business_facts={},
            customer_evidence=evidence_map, safe_fallback=safe_fallback,
            knowledge_required=decision.knowledge_required, booking_available=False,
            callback_at=analysis.requested_callback_at,
            human_takeover_active=decision.requires_human)
        generation = SalesResponseGenerationInput(
            approved_move=decision.move, sales_stage=decision.target_stage,
            channel=conversation.channel, customer_tone="neutral",
            knowledge_cards=[{"knowledge_id": card.knowledge_id,
                              "principle": card.principle} for card in knowledge],
            business_facts=[], customer_evidence=[
                {"evidence_id": key, "text": value} for key, value in evidence_map.items()],
            handoff_template=safe_fallback, safe_fallback_text=safe_fallback,
            conversation_context={"case_state": case.current_state.value},
            customer_message=customer.text)
        result = self._orchestrator.run(
            SalesShadowIdentity(job.business_id, job.case_id, job.conversation_id,
                                job.source_message_id), generation,
            validation_context=validation, delivered_response_text=delivered.text,
            now=now, persist_provider_errors=False)
        if result.status is SalesShadowStatus.VALIDATOR_ERROR:
            category = "validator_error"
        else:
            category = None
        self._complete(job, now, category=category)

    @staticmethod
    def _merge(profile: CustomerSalesProfile, analysis: Any) -> CustomerSalesProfile:
        values: dict[str, Any] = {}
        criteria = list(profile.decision_criteria)
        for signal in analysis.signals:
            if signal.kind in {"customer_goal", "current_problem", "desired_outcome"}:
                values[signal.kind] = signal.value
            elif signal.kind == "decision_criteria" and signal.value not in criteria:
                criteria.append(signal.value)
        values["decision_criteria"] = tuple(criteria)
        values["commitment_level"] = analysis.commitment_level
        if analysis.objections:
            values["active_objection"] = analysis.objections[0]
        return replace(profile, **values)

    def _record_terminal(self, job: SalesShadowJob, move: SalesMove,
                         delivered: str, category: str, now: datetime) -> None:
        from .sales_shadow_service import SalesShadowService
        SalesShadowService(self._uow_factory).record_error(
            SalesShadowIdentity(job.business_id, job.case_id, job.conversation_id,
                                job.source_message_id), approved_move=move,
            status=SalesShadowStatus.VALIDATOR_ERROR, violation=category,
            delivered_response_text=delivered, model_name=None, now=now)
        self._complete(job, now, category=category)

    def _complete(self, job: SalesShadowJob, now: datetime,
                  *, category: str | None = None) -> None:
        with self._uow_factory() as uow:
            if not uow.sales_shadow_jobs.complete(job.business_id, job.job_id,
                                                  lease_owner=self._worker_id, now=now):
                raise RuntimeError("shadow job lease was lost")
            uow.commit()
        LOGGER.info("sales_shadow_job_completed business_id=%s job_id=%s category=%s",
                    job.business_id, job.job_id, category or "success")

    def _retry(self, job: SalesShadowJob, category: str, now: datetime) -> None:
        delay = timedelta(seconds=min(3600, 30 * (2 ** job.retry_count)))
        with self._uow_factory() as uow:
            uow.sales_shadow_jobs.fail(job.business_id, job.job_id,
                lease_owner=self._worker_id, category=category,
                retry_at=now + delay, now=now)
            uow.commit()
        LOGGER.warning("sales_shadow_job_retry business_id=%s job_id=%s category=%s retry=%s",
                       job.business_id, job.job_id, category, job.retry_count + 1)


class ControlledShadowFailure(RuntimeError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category
