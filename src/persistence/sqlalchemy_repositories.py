"""Synchronous SQLAlchemy implementations of repository protocols."""

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.domain.models import Lead, ProcessCase, ProcessEvent, utc_now
from src.domain.conversations import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageDirection,
    MessageRole,
)
from src.domain.states import ProcessState
from src.domain.tenancy import Business, BusinessDNAVersion

from .errors import IdempotencyCollisionError, IdempotencyInProgressError, StaleCaseError
from .repositories import ClaimStatus, IdempotencyRecord
from .sqlalchemy_models import (
    BusinessDNARow,
    BusinessRow,
    ConversationMessageRow,
    ConversationRow,
    LeadRow,
    ProcessCaseRow,
    ProcessedMessageRow,
    ProcessEventRow,
)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set | frozenset):
        return [_json_value(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


class SQLAlchemyBusinessRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, business: Business) -> None:
        self.session.add(BusinessRow(
            id=business.business_id,
            name=business.name,
            created_at=business.created_at,
            updated_at=business.updated_at,
        ))

    def get(self, business_id: str) -> Business | None:
        row = self.session.get(BusinessRow, business_id)
        if row is None:
            return None
        return Business(row.id, row.name, _aware(row.created_at), _aware(row.updated_at))


class SQLAlchemyBusinessDNARepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_version(self, business_id: str, configuration: Mapping[str, Any]) -> BusinessDNAVersion:
        configured_business_id = configuration.get("business", {}).get("id")
        if configured_business_id != business_id:
            raise ValueError("Business DNA business.id must match its persisted tenant")
        business = self.session.scalar(
            select(BusinessRow).where(BusinessRow.id == business_id).with_for_update()
        )
        if business is None:
            raise KeyError(f"unknown business_id: {business_id}")
        latest = self.session.scalar(
            select(func.max(BusinessDNARow.version)).where(BusinessDNARow.business_id == business_id)
        ) or 0
        self.session.execute(
            update(BusinessDNARow)
            .where(BusinessDNARow.business_id == business_id, BusinessDNARow.active.is_(True))
            .values(active=False)
        )
        created_at = utc_now()
        row = BusinessDNARow(
            business_id=business_id,
            version=latest + 1,
            configuration=_json_value(configuration),
            created_at=created_at,
            active=True,
        )
        self.session.add(row)
        self.session.flush()
        return BusinessDNAVersion(business_id, row.version, row.configuration, created_at, True)

    def get_active(self, business_id: str) -> BusinessDNAVersion | None:
        row = self.session.scalar(select(BusinessDNARow).where(
            BusinessDNARow.business_id == business_id,
            BusinessDNARow.active.is_(True),
        ))
        return self._to_domain(row) if row else None

    def list_versions(self, business_id: str) -> tuple[BusinessDNAVersion, ...]:
        rows = self.session.scalars(
            select(BusinessDNARow)
            .where(BusinessDNARow.business_id == business_id)
            .order_by(BusinessDNARow.version)
        )
        return tuple(self._to_domain(row) for row in rows)

    @staticmethod
    def _to_domain(row: BusinessDNARow) -> BusinessDNAVersion:
        return BusinessDNAVersion(
            row.business_id, row.version, row.configuration, _aware(row.created_at), row.active
        )


class SQLAlchemyLeadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_identity(
        self,
        business_id: str,
        identity_type: str,
        normalized_value: str,
    ) -> None:
        """Serialize tenant identity claims across PostgreSQL workers."""

        if identity_type not in {"email", "phone"}:
            raise ValueError("unsupported lead identity type")
        if self.session.bind is None or self.session.bind.dialect.name != "postgresql":
            return
        identity = "\x1f".join(
            ("lead-identity", business_id, identity_type, normalized_value)
        )
        digest = hashlib.sha256(identity.encode("utf-8")).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    def add(self, business_id: str, lead: Lead, created_at: datetime) -> None:
        self.session.add(LeadRow(
            id=lead.lead_id,
            business_id=business_id,
            name=lead.name,
            phone=lead.phone,
            normalized_phone=lead.phone,
            email=lead.email,
            normalized_email=lead.email,
            metadata_json=_json_value(lead.attributes),
            created_at=created_at,
            updated_at=created_at,
        ))

    def save(self, business_id: str, lead: Lead, updated_at: datetime) -> None:
        result = self.session.execute(
            update(LeadRow)
            .where(LeadRow.business_id == business_id, LeadRow.id == lead.lead_id)
            .values(
                name=lead.name,
                phone=lead.phone,
                normalized_phone=lead.phone,
                email=lead.email,
                normalized_email=lead.email,
                metadata_json=_json_value(lead.attributes),
                updated_at=updated_at,
            )
        )
        if result.rowcount != 1:
            raise KeyError(f"lead not found for business: {lead.lead_id}")

    def get(self, business_id: str, lead_id: str) -> Lead | None:
        row = self.session.scalar(select(LeadRow).where(
            LeadRow.business_id == business_id, LeadRow.id == lead_id
        ))
        return self._to_domain(row) if row else None

    def find_by_identity(
        self,
        business_id: str,
        normalized_phone: str | None,
        normalized_email: str | None,
    ) -> Lead | None:
        ids: set[str] = set()
        if normalized_phone:
            ids.update(self.session.scalars(select(LeadRow.id).where(
                LeadRow.business_id == business_id,
                LeadRow.normalized_phone == normalized_phone,
            )))
        if normalized_email:
            ids.update(self.session.scalars(select(LeadRow.id).where(
                LeadRow.business_id == business_id,
                LeadRow.normalized_email == normalized_email,
            )))
        if len(ids) > 1:
            raise ValueError("message identifiers resolve to different existing leads")
        return self.get(business_id, next(iter(ids))) if ids else None

    @staticmethod
    def _to_domain(row: LeadRow) -> Lead:
        return Lead(row.id, row.name, row.email, row.phone, row.metadata_json)


class SQLAlchemyProcessEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, business_id: str, case_id: str, event: ProcessEvent) -> None:
        self.session.add(ProcessEventRow(
            id=event.event_id,
            business_id=business_id,
            case_id=case_id,
            event_type=str(event.event_type),
            trigger_id=event.causation_id,
            source=event.source,
            payload=_json_value(event.payload),
            occurred_at=event.occurred_at,
            created_at=utc_now(),
        ))

    def add_many(self, business_id: str, case_id: str, events: tuple[ProcessEvent, ...]) -> None:
        for event in events:
            self.add(business_id, case_id, event)

    def list_for_case(self, business_id: str, case_id: str) -> tuple[ProcessEvent, ...]:
        rows = self.session.scalars(
            select(ProcessEventRow)
            .where(
                ProcessEventRow.business_id == business_id,
                ProcessEventRow.case_id == case_id,
            )
            .order_by(ProcessEventRow.created_at, ProcessEventRow.id)
        )
        return tuple(ProcessEvent(
            event_type=row.event_type,
            event_id=row.id,
            occurred_at=_aware(row.occurred_at),
            payload=row.payload,
            source=row.source,
            causation_id=row.trigger_id,
        ) for row in rows)


class SQLAlchemyProcessCaseRepository:
    ACTIVE_STATES = (
        ProcessState.NEW_LEAD.value,
        ProcessState.CONTACTED.value,
        ProcessState.QUALIFYING.value,
        ProcessState.NEEDS_HUMAN.value,
    )

    def __init__(self, session: Session, events: SQLAlchemyProcessEventRepository) -> None:
        self.session = session
        self.events = events

    def add(self, case: ProcessCase) -> None:
        self.session.add(ProcessCaseRow(
            id=case.case_id,
            business_id=case.business_id,
            lead_id=case.lead.lead_id,
            current_state=case.current_state.value,
            pending_human_target=case.pending_transition.value if case.pending_transition else None,
            metadata_json=_json_value(case.metadata),
            created_at=case.created_at,
            updated_at=case.updated_at,
            version=case.version,
        ))

    def get(self, business_id: str, case_id: str) -> ProcessCase | None:
        row = self.session.scalar(select(ProcessCaseRow).where(
            ProcessCaseRow.business_id == business_id,
            ProcessCaseRow.id == case_id,
        ))
        return self._to_domain(row) if row else None

    def find_active_for_lead(self, business_id: str, lead_id: str) -> ProcessCase | None:
        row = self.session.scalar(
            select(ProcessCaseRow)
            .where(
                ProcessCaseRow.business_id == business_id,
                ProcessCaseRow.lead_id == lead_id,
                ProcessCaseRow.current_state.in_(self.ACTIVE_STATES),
            )
            .order_by(ProcessCaseRow.created_at.desc())
            .limit(1)
        )
        return self._to_domain(row) if row else None

    def save(self, case: ProcessCase, expected_version: int) -> None:
        new_version = expected_version + 1
        result = self.session.execute(
            update(ProcessCaseRow)
            .where(
                ProcessCaseRow.business_id == case.business_id,
                ProcessCaseRow.id == case.case_id,
                ProcessCaseRow.version == expected_version,
            )
            .values(
                lead_id=case.lead.lead_id,
                current_state=case.current_state.value,
                pending_human_target=case.pending_transition.value if case.pending_transition else None,
                metadata_json=_json_value(case.metadata),
                updated_at=case.updated_at,
                version=new_version,
            )
        )
        if result.rowcount != 1:
            raise StaleCaseError(f"case version conflict: {case.case_id}")
        case.mark_persisted(new_version)

    def _to_domain(self, row: ProcessCaseRow) -> ProcessCase:
        lead_row = self.session.scalar(select(LeadRow).where(
            LeadRow.business_id == row.business_id,
            LeadRow.id == row.lead_id,
        ))
        if lead_row is None:
            raise RuntimeError("process case references a missing tenant lead")
        lead = SQLAlchemyLeadRepository._to_domain(lead_row)
        return ProcessCase(
            row.id,
            row.business_id,
            lead,
            ProcessState(row.current_state),
            _aware(row.created_at),
            _aware(row.updated_at),
            row.metadata_json,
            version=row.version,
            pending_transition=ProcessState(row.pending_human_target) if row.pending_human_target else None,
            event_history=self.events.list_for_case(row.business_id, row.id),
        )


class SQLAlchemyIdempotencyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def claim(
        self,
        business_id: str,
        channel: str,
        external_message_id: str,
        fingerprint: str,
    ) -> tuple[ClaimStatus, IdempotencyRecord]:
        values = {
            "business_id": business_id,
            "channel": channel,
            "external_message_id": external_message_id,
            "message_fingerprint": fingerprint,
            "case_id": None,
            "result": None,
            "created_at": utc_now(),
        }
        dialect = self.session.get_bind().dialect.name
        if dialect == "postgresql":
            self._lock_message_identity(business_id, channel, external_message_id)
            statement = postgresql_insert(ProcessedMessageRow).values(**values).on_conflict_do_nothing(
                index_elements=["business_id", "channel", "external_message_id"]
            ).returning(ProcessedMessageRow.business_id)
        elif dialect == "sqlite":
            statement = sqlite_insert(ProcessedMessageRow).values(**values).on_conflict_do_nothing(
                index_elements=["business_id", "channel", "external_message_id"]
            ).returning(ProcessedMessageRow.business_id)
        else:
            raise RuntimeError(f"idempotency claims are unsupported for database dialect: {dialect}")
        inserted = self.session.scalar(statement) is not None
        record = self.get(business_id, channel, external_message_id)
        if record is None:
            raise RuntimeError("idempotency claim was not visible in its transaction")
        if not inserted and record.fingerprint != fingerprint:
            raise IdempotencyCollisionError("message identity was reused with a different fingerprint")
        if not inserted and record.result is None:
            raise IdempotencyInProgressError("message claim exists without a completed result")
        return (ClaimStatus.CLAIMED if inserted else ClaimStatus.COMPLETED), record

    def _lock_message_identity(self, business_id: str, channel: str, external_message_id: str) -> None:
        identity = "\x1f".join((business_id, channel, external_message_id))
        digest = hashlib.sha256(identity.encode("utf-8")).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    def complete(
        self,
        business_id: str,
        channel: str,
        external_message_id: str,
        case_id: str,
        result: Mapping[str, Any],
    ) -> None:
        updated = self.session.execute(
            update(ProcessedMessageRow)
            .where(
                ProcessedMessageRow.business_id == business_id,
                ProcessedMessageRow.channel == channel,
                ProcessedMessageRow.external_message_id == external_message_id,
                ProcessedMessageRow.result.is_(None),
            )
            .values(case_id=case_id, result=_json_value(result))
        )
        if updated.rowcount != 1:
            raise RuntimeError("idempotency claim could not be completed exactly once")

    def get(self, business_id: str, channel: str, external_message_id: str) -> IdempotencyRecord | None:
        row = self.session.scalar(select(ProcessedMessageRow).where(
            ProcessedMessageRow.business_id == business_id,
            ProcessedMessageRow.channel == channel,
            ProcessedMessageRow.external_message_id == external_message_id,
        ))
        if row is None:
            return None
        return IdempotencyRecord(
            row.business_id,
            row.channel,
            row.external_message_id,
            row.message_fingerprint,
            row.case_id,
            row.result,
            _aware(row.created_at),
        )


class SQLAlchemyConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_token_identity(self, business_id: str, token_hash: str) -> None:
        if self.session.get_bind().dialect.name != "postgresql":
            return
        identity = f"conversation-token\x1f{business_id}\x1f{token_hash}"
        digest = hashlib.sha256(identity.encode("utf-8")).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    def add(self, conversation: Conversation) -> None:
        self.session.add(ConversationRow(
            id=conversation.conversation_id,
            business_id=conversation.business_id,
            token_hash=conversation.token_hash,
            channel=conversation.channel,
            lead_id=conversation.lead_id,
            case_id=conversation.case_id,
            external_session_id=conversation.external_session_id,
            status=conversation.status.value,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            last_activity_at=conversation.last_activity_at,
            token_expires_at=conversation.token_expires_at,
            token_revoked_at=conversation.token_revoked_at,
            metadata_json=_json_value(conversation.metadata),
            version=conversation.version,
        ))

    def get(
        self,
        business_id: str,
        conversation_id: str,
        *,
        for_update: bool = False,
    ) -> Conversation | None:
        statement = select(ConversationRow).where(
            ConversationRow.business_id == business_id,
            ConversationRow.id == conversation_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._to_domain(row) if row is not None else None

    def get_by_token_hash(
        self,
        business_id: str,
        token_hash: str,
        *,
        for_update: bool = False,
    ) -> Conversation | None:
        statement = select(ConversationRow).where(
            ConversationRow.business_id == business_id,
            ConversationRow.token_hash == token_hash,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._to_domain(row) if row is not None else None

    def save(self, conversation: Conversation, expected_version: int) -> None:
        new_version = expected_version + 1
        result = self.session.execute(
            update(ConversationRow)
            .where(
                ConversationRow.business_id == conversation.business_id,
                ConversationRow.id == conversation.conversation_id,
                ConversationRow.version == expected_version,
            )
            .values(
                lead_id=conversation.lead_id,
                case_id=conversation.case_id,
                status=conversation.status.value,
                updated_at=conversation.updated_at,
                last_activity_at=conversation.last_activity_at,
                token_expires_at=conversation.token_expires_at,
                token_revoked_at=conversation.token_revoked_at,
                metadata_json=_json_value(conversation.metadata),
                version=new_version,
            )
        )
        if result.rowcount != 1:
            raise StaleCaseError(f"conversation version conflict: {conversation.conversation_id}")
        conversation.mark_persisted(new_version)

    @staticmethod
    def _to_domain(row: ConversationRow) -> Conversation:
        return Conversation(
            conversation_id=row.id,
            business_id=row.business_id,
            token_hash=row.token_hash,
            channel=row.channel,
            status=ConversationStatus(row.status),
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
            last_activity_at=_aware(row.last_activity_at),
            token_expires_at=_aware(row.token_expires_at),
            lead_id=row.lead_id,
            case_id=row.case_id,
            external_session_id=row.external_session_id,
            token_revoked_at=_aware(row.token_revoked_at) if row.token_revoked_at else None,
            metadata=row.metadata_json,
            version=row.version,
        )


class SQLAlchemyConversationMessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, message: ConversationMessage) -> None:
        self.session.add(ConversationMessageRow(
            id=message.message_id,
            business_id=message.business_id,
            conversation_id=message.conversation_id,
            sequence_number=message.sequence_number,
            direction=message.direction.value,
            role=message.role.value,
            text=message.text,
            created_at=message.created_at,
            external_message_id=message.external_message_id,
            content_fingerprint=message.content_fingerprint,
            correlation_id=message.correlation_id,
            metadata_json=_json_value(message.metadata),
        ))

    def get_by_external_id(
        self,
        business_id: str,
        conversation_id: str,
        external_message_id: str,
    ) -> ConversationMessage | None:
        row = self.session.scalar(select(ConversationMessageRow).where(
            ConversationMessageRow.business_id == business_id,
            ConversationMessageRow.conversation_id == conversation_id,
            ConversationMessageRow.external_message_id == external_message_id,
        ))
        return self._to_domain(row) if row is not None else None

    def list_for_conversation(
        self,
        business_id: str,
        conversation_id: str,
        *,
        limit: int | None = None,
    ) -> tuple[ConversationMessage, ...]:
        statement = (
            select(ConversationMessageRow)
            .where(
                ConversationMessageRow.business_id == business_id,
                ConversationMessageRow.conversation_id == conversation_id,
            )
            .order_by(ConversationMessageRow.sequence_number.desc())
        )
        if limit is not None:
            if limit < 1:
                return ()
            statement = statement.limit(limit)
        rows = tuple(self.session.scalars(statement))
        return tuple(self._to_domain(row) for row in reversed(rows))

    def next_sequence(self, business_id: str, conversation_id: str) -> int:
        latest = self.session.scalar(
            select(func.max(ConversationMessageRow.sequence_number)).where(
                ConversationMessageRow.business_id == business_id,
                ConversationMessageRow.conversation_id == conversation_id,
            )
        )
        return int(latest or 0) + 1

    @staticmethod
    def _to_domain(row: ConversationMessageRow) -> ConversationMessage:
        return ConversationMessage(
            message_id=row.id,
            business_id=row.business_id,
            conversation_id=row.conversation_id,
            sequence_number=row.sequence_number,
            direction=MessageDirection(row.direction),
            role=MessageRole(row.role),
            text=row.text,
            created_at=_aware(row.created_at),
            external_message_id=row.external_message_id,
            content_fingerprint=row.content_fingerprint,
            correlation_id=row.correlation_id,
            metadata=row.metadata_json,
        )
