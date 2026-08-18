"""Synchronous SQLAlchemy implementations of repository protocols."""

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.domain.auth import StaffSession, StaffUser
from src.domain.models import Lead, ProcessCase, ProcessEvent, utc_now
from src.domain.commercial import (
    Booking,
    BookingStatus,
    PaymentRequest,
    PaymentStatus,
    PaymentType,
    Quote,
    QuoteLine,
    QuoteStatus,
)
from src.domain.conversations import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageDirection,
    MessageRole,
)
from src.domain.states import ProcessState
from src.domain.tenancy import Business, BusinessDNAVersion

from .errors import (
    IdempotencyCollisionError,
    IdempotencyInProgressError,
    StaleBookingError,
    StaleCaseError,
    StalePaymentRequestError,
    StaleQuoteError,
)
from .repositories import ClaimStatus, IdempotencyRecord
from .sqlalchemy_models import (
    BusinessDNARow,
    BusinessRow,
    BookingRow,
    ConversationMessageRow,
    ConversationRow,
    CrmWebhookConnectionRow,
    SmsConnectionRow,
    LeadRow,
    PaymentRequestRow,
    ProcessCaseRow,
    ProcessedMessageRow,
    ProcessEventRow,
    QuoteLineRow,
    QuoteRow,
    StaffSessionRow,
    StaffUserRow,
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


def _business_from_row(row: BusinessRow) -> Business:
    return Business(
        row.id,
        row.name,
        _aware(row.created_at),
        _aware(row.updated_at),
        payment_customer_id=row.payment_customer_id,
        payment_subscription_id=row.payment_subscription_id,
        plan=row.plan,
        subscription_status=row.subscription_status,
        trial_ends_at=_aware(row.trial_ends_at) if row.trial_ends_at else None,
        current_period_end=_aware(row.current_period_end) if row.current_period_end else None,
    )


class SQLAlchemyBusinessRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, business: Business) -> None:
        self.session.add(BusinessRow(
            id=business.business_id,
            name=business.name,
            created_at=business.created_at,
            updated_at=business.updated_at,
            payment_customer_id=business.payment_customer_id,
            payment_subscription_id=business.payment_subscription_id,
            plan=business.plan,
            subscription_status=business.subscription_status,
            trial_ends_at=business.trial_ends_at,
            current_period_end=business.current_period_end,
        ))

    def get(self, business_id: str) -> Business | None:
        row = self.session.get(BusinessRow, business_id)
        if row is None:
            return None
        return _business_from_row(row)

    def get_by_payment_customer_id(self, payment_customer_id: str) -> Business | None:
        """Fallback lookup only (see BillingService._resolve_business_id --
        webhook events resolve via custom_data.business_id first). Not
        unique since migration 0009: the same Lemon Squeezy customer_id can
        legitimately belong to more than one business (one email running
        several businesses through this app) -- if more than one row
        matches, this returns an arbitrary one of them, same as .scalar()
        always has for a non-unique column."""
        row = self.session.scalar(
            select(BusinessRow).where(BusinessRow.payment_customer_id == payment_customer_id)
        )
        if row is None:
            return None
        return _business_from_row(row)

    def get_by_payment_subscription_id(self, payment_subscription_id: str) -> Business | None:
        row = self.session.scalar(
            select(BusinessRow).where(BusinessRow.payment_subscription_id == payment_subscription_id)
        )
        if row is None:
            return None
        return _business_from_row(row)

    def update_billing(
        self,
        business_id: str,
        *,
        payment_customer_id: str | None,
        payment_subscription_id: str | None,
        plan: str | None,
        subscription_status: str,
        trial_ends_at: datetime | None,
        current_period_end: datetime | None,
    ) -> Business:
        row = self.session.scalar(
            select(BusinessRow).where(BusinessRow.id == business_id).with_for_update()
        )
        if row is None:
            raise KeyError(f"unknown business_id: {business_id}")
        if payment_customer_id is not None:
            row.payment_customer_id = payment_customer_id
        if payment_subscription_id is not None:
            row.payment_subscription_id = payment_subscription_id
        if plan is not None:
            row.plan = plan
        row.subscription_status = subscription_status
        row.trial_ends_at = trial_ends_at
        row.current_period_end = current_period_end
        row.updated_at = utc_now()
        self.session.flush()
        return _business_from_row(row)


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


class SQLAlchemyCrmWebhookConnectionRepository:
    """One outbound CRM webhook URL per business. See CrmWebhookConnectionRow
    for why this is its own table rather than a Business DNA field."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_url(self, business_id: str) -> str | None:
        row = self.session.get(CrmWebhookConnectionRow, business_id)
        return row.webhook_url if row is not None else None

    def upsert(self, business_id: str, webhook_url: str, *, now: datetime) -> None:
        row = self.session.get(CrmWebhookConnectionRow, business_id)
        if row is None:
            self.session.add(CrmWebhookConnectionRow(
                business_id=business_id,
                webhook_url=webhook_url,
                created_at=now,
                updated_at=now,
            ))
        else:
            row.webhook_url = webhook_url
            row.updated_at = now

    def delete(self, business_id: str) -> None:
        row = self.session.get(CrmWebhookConnectionRow, business_id)
        if row is not None:
            self.session.delete(row)


class SQLAlchemySmsConnectionRepository:
    """One purchased Twilio phone number per business. See SmsConnectionRow."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_business(self, business_id: str) -> tuple[str, str] | None:
        row = self.session.get(SmsConnectionRow, business_id)
        return (row.phone_number, row.twilio_phone_sid) if row is not None else None

    def get_business_id_by_phone(self, phone_number: str) -> str | None:
        row = (
            self.session.query(SmsConnectionRow)
            .filter(SmsConnectionRow.phone_number == phone_number)
            .one_or_none()
        )
        return row.business_id if row is not None else None

    def add(
        self, business_id: str, phone_number: str, twilio_phone_sid: str, *, now: datetime
    ) -> None:
        self.session.add(SmsConnectionRow(
            business_id=business_id,
            phone_number=phone_number,
            twilio_phone_sid=twilio_phone_sid,
            created_at=now,
            updated_at=now,
        ))


class SQLAlchemyStaffUserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, user: StaffUser) -> None:
        self.session.add(StaffUserRow(
            id=user.user_id,
            business_id=user.business_id,
            email=user.email,
            normalized_email=user.normalized_email,
            password_hash=user.password_hash,
            created_at=user.created_at,
        ))
        # Flush so the row exists before a StaffSession referencing this
        # user_id is inserted later in the same unit of work (signup issues
        # a session immediately after creating the user) — Postgres checks
        # non-deferrable foreign keys per-statement, not at commit time.
        self.session.flush()

    def get(self, user_id: str) -> StaffUser | None:
        row = self.session.get(StaffUserRow, user_id)
        return self._to_domain(row) if row else None

    def get_by_email(self, normalized_email: str) -> StaffUser | None:
        row = self.session.scalar(
            select(StaffUserRow).where(StaffUserRow.normalized_email == normalized_email)
        )
        return self._to_domain(row) if row else None

    def save(self, user: StaffUser) -> None:
        row = self.session.get(StaffUserRow, user.user_id)
        if row is None:
            raise KeyError(f"unknown staff user_id: {user.user_id}")
        row.business_id = user.business_id
        row.email = user.email
        row.password_hash = user.password_hash

    @staticmethod
    def _to_domain(row: StaffUserRow) -> StaffUser:
        return StaffUser(
            row.id, row.email, row.normalized_email, row.password_hash,
            row.business_id, _aware(row.created_at),
        )


class SQLAlchemyStaffSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, session: StaffSession) -> None:
        self.session.add(StaffSessionRow(
            id=session.session_id,
            user_id=session.user_id,
            token_hash=session.token_hash,
            created_at=session.created_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
        ))

    def get_by_token_hash(self, token_hash: str) -> StaffSession | None:
        row = self.session.scalar(
            select(StaffSessionRow).where(StaffSessionRow.token_hash == token_hash)
        )
        return self._to_domain(row) if row else None

    def revoke(self, session_id: str, revoked_at: datetime) -> None:
        row = self.session.get(StaffSessionRow, session_id)
        if row is None:
            raise KeyError(f"unknown session_id: {session_id}")
        row.revoked_at = revoked_at

    @staticmethod
    def _to_domain(row: StaffSessionRow) -> StaffSession:
        return StaffSession(
            row.id, row.user_id, row.token_hash, _aware(row.created_at), _aware(row.expires_at),
            _aware(row.revoked_at) if row.revoked_at is not None else None,
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

    def list_for_business(self, business_id: str, *, limit: int = 200) -> tuple[ProcessCase, ...]:
        rows = self.session.scalars(
            select(ProcessCaseRow)
            .where(ProcessCaseRow.business_id == business_id)
            .order_by(ProcessCaseRow.updated_at.desc())
            .limit(limit)
        )
        return tuple(self._to_domain(row) for row in rows)

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

    def list_for_business(self, business_id: str, *, limit: int = 200) -> tuple[Conversation, ...]:
        rows = self.session.scalars(
            select(ConversationRow)
            .where(ConversationRow.business_id == business_id)
            .order_by(ConversationRow.last_activity_at.desc())
            .limit(limit)
        )
        return tuple(self._to_domain(row) for row in rows)

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


class SQLAlchemyBookingRepository:
    ACTIVE_STATUSES = (
        BookingStatus.PENDING.value,
        BookingStatus.CONFIRMED.value,
        BookingStatus.RESCHEDULED.value,
    )

    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_slot(self, business_id: str, service_id: str, start_at: datetime) -> None:
        if self.session.get_bind().dialect.name != "postgresql":
            return
        # Serialize a tenant/service schedule, not merely an exact start time:
        # appointments with different starts can still overlap through duration
        # or configured buffers.
        identity = "\x1f".join(("booking-schedule", business_id, service_id))
        digest = hashlib.sha256(identity.encode("utf-8")).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    def add(self, booking: Booking) -> None:
        self.session.add(BookingRow(
            id=booking.booking_id,
            business_id=booking.business_id,
            case_id=booking.case_id,
            lead_id=booking.lead_id,
            service_id=booking.service_id,
            start_at=booking.start_at,
            end_at=booking.end_at,
            timezone=booking.timezone,
            status=booking.status.value,
            created_at=booking.created_at,
            updated_at=booking.updated_at,
            metadata_json=_json_value(booking.metadata),
            version=booking.version,
        ))

    def get(
        self,
        business_id: str,
        booking_id: str,
        *,
        for_update: bool = False,
    ) -> Booking | None:
        statement = select(BookingRow).where(
            BookingRow.business_id == business_id,
            BookingRow.id == booking_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._to_domain(row) if row is not None else None

    def get_for_case(
        self,
        business_id: str,
        case_id: str,
        *,
        for_update: bool = False,
    ) -> Booking | None:
        statement = select(BookingRow).where(
            BookingRow.business_id == business_id,
            BookingRow.case_id == case_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._to_domain(row) if row is not None else None

    def list_overlapping(
        self,
        business_id: str,
        service_id: str,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_booking_id: str | None = None,
    ) -> tuple[Booking, ...]:
        statement = select(BookingRow).where(
            BookingRow.business_id == business_id,
            BookingRow.service_id == service_id,
            BookingRow.status.in_(self.ACTIVE_STATUSES),
            BookingRow.start_at < end_at,
            BookingRow.end_at > start_at,
        )
        if exclude_booking_id is not None:
            statement = statement.where(BookingRow.id != exclude_booking_id)
        return tuple(self._to_domain(row) for row in self.session.scalars(statement))

    def save(self, booking: Booking, expected_version: int) -> None:
        new_version = expected_version + 1
        result = self.session.execute(
            update(BookingRow)
            .where(
                BookingRow.business_id == booking.business_id,
                BookingRow.id == booking.booking_id,
                BookingRow.version == expected_version,
            )
            .values(
                start_at=booking.start_at,
                end_at=booking.end_at,
                timezone=booking.timezone,
                status=booking.status.value,
                updated_at=booking.updated_at,
                metadata_json=_json_value(booking.metadata),
                version=new_version,
            )
        )
        if result.rowcount != 1:
            raise StaleBookingError(f"booking version conflict: {booking.booking_id}")
        booking.mark_persisted(new_version)

    @staticmethod
    def _to_domain(row: BookingRow) -> Booking:
        return Booking(
            booking_id=row.id,
            business_id=row.business_id,
            case_id=row.case_id,
            lead_id=row.lead_id,
            service_id=row.service_id,
            start_at=_aware(row.start_at).astimezone(timezone.utc),
            end_at=_aware(row.end_at).astimezone(timezone.utc),
            timezone=row.timezone,
            status=BookingStatus(row.status),
            created_at=_aware(row.created_at).astimezone(timezone.utc),
            updated_at=_aware(row.updated_at).astimezone(timezone.utc),
            metadata=row.metadata_json,
            version=row.version,
        )


class SQLAlchemyQuoteRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, quote: Quote) -> None:
        self.session.add(QuoteRow(
            id=quote.quote_id,
            business_id=quote.business_id,
            case_id=quote.case_id,
            lead_id=quote.lead_id,
            service_id=quote.service_id,
            currency=quote.currency,
            subtotal=quote.subtotal,
            total=quote.total,
            valid_until=quote.valid_until,
            status=quote.status.value,
            created_at=quote.created_at,
            updated_at=quote.updated_at,
            pricing_basis=_json_value(quote.pricing_basis),
            metadata_json=_json_value(quote.metadata),
            version=quote.version,
        ))
        # The mappings intentionally have no ORM relationships. Flush the
        # parent explicitly so composite tenant foreign keys on lines are
        # satisfied consistently on both SQLite and PostgreSQL.
        self.session.flush()
        for position, line in enumerate(quote.lines, start=1):
            self.session.add(QuoteLineRow(
                id=f"{quote.quote_id}:{line.line_id}",
                business_id=quote.business_id,
                quote_id=quote.quote_id,
                position=position,
                description=line.description,
                quantity=line.quantity,
                unit_amount=line.unit_amount,
                line_total=line.line_total,
            ))

    def get(
        self,
        business_id: str,
        quote_id: str,
        *,
        for_update: bool = False,
    ) -> Quote | None:
        statement = select(QuoteRow).where(
            QuoteRow.business_id == business_id,
            QuoteRow.id == quote_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._to_domain(row) if row is not None else None

    def get_for_case(
        self,
        business_id: str,
        case_id: str,
        *,
        for_update: bool = False,
    ) -> Quote | None:
        statement = select(QuoteRow).where(
            QuoteRow.business_id == business_id,
            QuoteRow.case_id == case_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._to_domain(row) if row is not None else None

    def save(self, quote: Quote, expected_version: int) -> None:
        new_version = expected_version + 1
        result = self.session.execute(
            update(QuoteRow)
            .where(
                QuoteRow.business_id == quote.business_id,
                QuoteRow.id == quote.quote_id,
                QuoteRow.version == expected_version,
            )
            .values(
                status=quote.status.value,
                updated_at=quote.updated_at,
                metadata_json=_json_value(quote.metadata),
                version=new_version,
            )
        )
        if result.rowcount != 1:
            raise StaleQuoteError(f"quote version conflict: {quote.quote_id}")
        quote.mark_persisted(new_version)

    def _to_domain(self, row: QuoteRow) -> Quote:
        line_rows = tuple(self.session.scalars(
            select(QuoteLineRow)
            .where(
                QuoteLineRow.business_id == row.business_id,
                QuoteLineRow.quote_id == row.id,
            )
            .order_by(QuoteLineRow.position)
        ))
        lines = tuple(QuoteLine(
            line_id=line_row.id.removeprefix(f"{row.id}:"),
            description=line_row.description,
            quantity=line_row.quantity,
            unit_amount=line_row.unit_amount,
            line_total=line_row.line_total,
        ) for line_row in line_rows)
        return Quote(
            quote_id=row.id,
            business_id=row.business_id,
            case_id=row.case_id,
            lead_id=row.lead_id,
            service_id=row.service_id,
            currency=row.currency,
            subtotal=row.subtotal,
            total=row.total,
            valid_until=_aware(row.valid_until).astimezone(timezone.utc),
            status=QuoteStatus(row.status),
            created_at=_aware(row.created_at).astimezone(timezone.utc),
            updated_at=_aware(row.updated_at).astimezone(timezone.utc),
            pricing_basis=row.pricing_basis,
            lines=lines,
            metadata=row.metadata_json,
            version=row.version,
        )


class SQLAlchemyPaymentRequestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, payment_request: PaymentRequest) -> None:
        self.session.add(PaymentRequestRow(
            id=payment_request.payment_request_id,
            business_id=payment_request.business_id,
            case_id=payment_request.case_id,
            quote_id=payment_request.quote_id,
            booking_id=payment_request.booking_id,
            amount=payment_request.amount,
            currency=payment_request.currency,
            payment_type=payment_request.payment_type.value,
            status=payment_request.status.value,
            created_at=payment_request.created_at,
            updated_at=payment_request.updated_at,
            expires_at=payment_request.expires_at,
            metadata_json=_json_value(payment_request.metadata),
            version=payment_request.version,
        ))

    def get(
        self,
        business_id: str,
        payment_request_id: str,
        *,
        for_update: bool = False,
    ) -> PaymentRequest | None:
        statement = select(PaymentRequestRow).where(
            PaymentRequestRow.business_id == business_id,
            PaymentRequestRow.id == payment_request_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._to_domain(row) if row is not None else None

    def get_for_case_type(
        self,
        business_id: str,
        case_id: str,
        payment_type: PaymentType,
        *,
        for_update: bool = False,
    ) -> PaymentRequest | None:
        statement = select(PaymentRequestRow).where(
            PaymentRequestRow.business_id == business_id,
            PaymentRequestRow.case_id == case_id,
            PaymentRequestRow.payment_type == payment_type.value,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._to_domain(row) if row is not None else None

    def save(self, payment_request: PaymentRequest, expected_version: int) -> None:
        new_version = expected_version + 1
        result = self.session.execute(
            update(PaymentRequestRow)
            .where(
                PaymentRequestRow.business_id == payment_request.business_id,
                PaymentRequestRow.id == payment_request.payment_request_id,
                PaymentRequestRow.version == expected_version,
            )
            .values(
                status=payment_request.status.value,
                updated_at=payment_request.updated_at,
                version=new_version,
            )
        )
        if result.rowcount != 1:
            raise StalePaymentRequestError(
                f"payment request version conflict: {payment_request.payment_request_id}"
            )
        payment_request.mark_persisted(new_version)

    @staticmethod
    def _to_domain(row: PaymentRequestRow) -> PaymentRequest:
        return PaymentRequest(
            payment_request_id=row.id,
            business_id=row.business_id,
            case_id=row.case_id,
            quote_id=row.quote_id,
            booking_id=row.booking_id,
            amount=row.amount,
            currency=row.currency,
            payment_type=PaymentType(row.payment_type),
            status=PaymentStatus(row.status),
            created_at=_aware(row.created_at).astimezone(timezone.utc),
            updated_at=_aware(row.updated_at).astimezone(timezone.utc),
            expires_at=_aware(row.expires_at).astimezone(timezone.utc),
            metadata=row.metadata_json,
            version=row.version,
        )
