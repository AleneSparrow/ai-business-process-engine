"""Synchronous SQLAlchemy implementations of repository protocols."""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.domain.auth import StaffSession, StaffUser
from src.domain.signup_attribution import SignupAttribution
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
from .repositories import ClaimStatus, DeliveryStatus, FollowUpDeliveryAttempt, IdempotencyRecord
from .repositories import (
    LoginChallenge, PasswordResetRecord, RecoveryCode, SecurityAuditEvent,
    SecurityCredentials,
)
from .sqlalchemy_models import (
    BillingWebhookEventRow,
    BusinessDNARow,
    BusinessRow,
    BookingRow,
    ConversationMessageRow,
    ConversationRow,
    CrmWebhookConnectionRow,
    FollowUpDeliveryAttemptRow,
    SmsConnectionRow,
    LeadRow,
    PaymentRequestRow,
    ProcessCaseRow,
    ProcessedMessageRow,
    ProcessEventRow,
    QuoteLineRow,
    QuoteRow,
    StaffSessionRow,
    StaffSignupAttributionRow,
    StaffSecurityCredentialRow,
    StaffPasswordResetRow,
    StaffLoginChallengeRow,
    StaffRecoveryCodeRow,
    StaffSecurityAuditEventRow,
    BusinessMembershipRow,
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
        billing_event_at=_aware(row.billing_event_at) if row.billing_event_at else None,
        test_mode_enabled=row.test_mode_enabled,
        stats_since=_aware(row.stats_since) if row.stats_since else None,
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
            billing_event_at=business.billing_event_at,
            test_mode_enabled=business.test_mode_enabled,
            stats_since=business.stats_since,
        ))

    def get(self, business_id: str) -> Business | None:
        row = self.session.get(BusinessRow, business_id)
        if row is None:
            return None
        return _business_from_row(row)

    def get_by_payment_customer_id(self, payment_customer_id: str) -> Business | None:
        """Return an owner only when the fallback identity is unambiguous.

        Lemon Squeezy reuses a customer ID when one person owns multiple
        businesses.  Treating that non-unique value as an owner would let a
        signed, but metadata-less, webhook update an arbitrary tenant.
        """
        rows = self.session.scalars(
            select(BusinessRow)
            .where(BusinessRow.payment_customer_id == payment_customer_id)
            .limit(2)
        ).all()
        if len(rows) != 1:
            return None
        return _business_from_row(rows[0])

    def get_by_payment_subscription_id(self, payment_subscription_id: str) -> Business | None:
        # Provider subscription IDs are expected to be unique, but the
        # schema intentionally does not make a historical data anomaly a
        # cross-tenant write.  Fail closed unless there is exactly one owner.
        rows = self.session.scalars(
            select(BusinessRow)
            .where(BusinessRow.payment_subscription_id == payment_subscription_id)
            .limit(2)
        ).all()
        if len(rows) != 1:
            return None
        return _business_from_row(rows[0])

    def list_all(self) -> tuple[Business, ...]:
        rows = self.session.scalars(select(BusinessRow).order_by(BusinessRow.id))
        return tuple(_business_from_row(row) for row in rows)

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
        event_at: datetime | None = None,
    ) -> Business:
        row = self.session.scalar(
            select(BusinessRow).where(BusinessRow.id == business_id).with_for_update()
        )
        if row is None:
            raise KeyError(f"unknown business_id: {business_id}")
        stored_event_at = _aware(row.billing_event_at) if row.billing_event_at else None
        if stored_event_at is not None and (event_at is None or event_at < stored_event_at):
            # Out-of-order delivery: a newer billing snapshot (by event_at)
            # has already been applied. An event without a comparable time is
            # equally unsafe: it cannot prove it is newer, so it must not
            # resurrect access after cancellation/expiry.
            return _business_from_row(row)
        if payment_customer_id is not None:
            row.payment_customer_id = payment_customer_id
        if payment_subscription_id is not None:
            row.payment_subscription_id = payment_subscription_id
        if plan is not None:
            row.plan = plan
        row.subscription_status = subscription_status
        row.trial_ends_at = trial_ends_at
        row.current_period_end = current_period_end
        if event_at is not None:
            row.billing_event_at = event_at
        row.updated_at = utc_now()
        self.session.flush()
        return _business_from_row(row)

    def update_reporting_settings(
        self,
        business_id: str,
        *,
        test_mode_enabled: bool | None = None,
        stats_since: datetime | None = None,
        clear_stats_since: bool = False,
    ) -> Business:
        if clear_stats_since and stats_since is not None:
            raise ValueError("stats_since and clear_stats_since are mutually exclusive")
        row = self.session.scalar(
            select(BusinessRow).where(BusinessRow.id == business_id).with_for_update()
        )
        if row is None:
            raise KeyError(f"unknown business_id: {business_id}")
        if test_mode_enabled is not None:
            row.test_mode_enabled = test_mode_enabled
        if clear_stats_since:
            row.stats_since = None
        elif stats_since is not None:
            row.stats_since = stats_since
        row.updated_at = utc_now()
        self.session.flush()
        return _business_from_row(row)


class SQLAlchemyBillingWebhookEventRepository:
    """See BillingWebhookEventRow for why this exists and stores no payload
    or customer data."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def claim(self, event_fingerprint: str, event_name: str, *, now: datetime) -> bool:
        values = {
            "event_fingerprint": event_fingerprint,
            "event_name": event_name,
            "processed_at": now,
        }
        dialect = self.session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(BillingWebhookEventRow).values(**values).on_conflict_do_nothing(
                index_elements=["event_fingerprint"]
            ).returning(BillingWebhookEventRow.event_fingerprint)
        elif dialect == "sqlite":
            statement = sqlite_insert(BillingWebhookEventRow).values(**values).on_conflict_do_nothing(
                index_elements=["event_fingerprint"]
            ).returning(BillingWebhookEventRow.event_fingerprint)
        else:
            raise RuntimeError(f"billing webhook dedup is unsupported for database dialect: {dialect}")
        return self.session.scalar(statement) is not None


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


# A PENDING row older than this is treated as abandoned -- the process that
# claimed it crashed somewhere between claiming and recording an outcome
# (most likely mid-Twilio-call) -- and a later claimer is allowed to take
# over rather than leave the case stuck retrying forever. This is the one
# place a duplicate send remains possible (the original claimer may or may
# not have actually reached Twilio before crashing); see
# FollowUpDeliveryAttemptRow and PersistentFollowUpRunner._send_one for why
# that's an accepted, narrowed trade-off, not the common case.
_ABANDONED_ATTEMPT_GRACE = timedelta(minutes=5)


class SQLAlchemyFollowUpDeliveryRepository:
    """Durable outbox for proactive follow-up SMS. See
    FollowUpDeliveryAttemptRow for the concurrency/idempotency reasoning."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def claim_attempt(
        self,
        business_id: str,
        case_id: str,
        attempt_number: int,
        *,
        message_text: str,
        now: datetime,
    ) -> tuple[FollowUpDeliveryAttempt, bool]:
        values = {
            "business_id": business_id,
            "case_id": case_id,
            "attempt_number": attempt_number,
            "status": DeliveryStatus.PENDING.value,
            "message_text": message_text,
            "twilio_sid": None,
            "created_at": now,
            "updated_at": now,
        }
        index_elements = ["business_id", "case_id", "attempt_number"]
        dialect = self.session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(FollowUpDeliveryAttemptRow).values(**values).on_conflict_do_nothing(
                index_elements=index_elements
            ).returning(FollowUpDeliveryAttemptRow.business_id)
        elif dialect == "sqlite":
            statement = sqlite_insert(FollowUpDeliveryAttemptRow).values(**values).on_conflict_do_nothing(
                index_elements=index_elements
            ).returning(FollowUpDeliveryAttemptRow.business_id)
        else:
            raise RuntimeError(f"follow-up delivery claims are unsupported for database dialect: {dialect}")
        inserted = self.session.scalar(statement) is not None
        if inserted:
            row = self.session.get(FollowUpDeliveryAttemptRow, (business_id, case_id, attempt_number))
            if row is None:
                raise RuntimeError("follow-up delivery claim was not visible in its transaction")
            return self._to_domain(row), True

        # Someone else already claimed this attempt. Only take over if their
        # claim looks abandoned (still PENDING well past the grace period) --
        # an atomic conditional UPDATE, so two callers racing to "take over"
        # the same stuck row still can't both win.
        cutoff = now - _ABANDONED_ATTEMPT_GRACE
        takeover = self.session.execute(
            update(FollowUpDeliveryAttemptRow)
            .where(
                FollowUpDeliveryAttemptRow.business_id == business_id,
                FollowUpDeliveryAttemptRow.case_id == case_id,
                FollowUpDeliveryAttemptRow.attempt_number == attempt_number,
                FollowUpDeliveryAttemptRow.status == DeliveryStatus.PENDING.value,
                FollowUpDeliveryAttemptRow.updated_at < cutoff,
            )
            .values(updated_at=now)
        )
        owns_send = takeover.rowcount == 1
        row = self.session.get(FollowUpDeliveryAttemptRow, (business_id, case_id, attempt_number))
        if row is None:
            raise RuntimeError("follow-up delivery claim was not visible in its transaction")
        return self._to_domain(row), owns_send

    def mark_result(
        self,
        business_id: str,
        case_id: str,
        attempt_number: int,
        *,
        sent: bool,
        twilio_sid: str | None,
        now: datetime,
    ) -> None:
        self.session.execute(
            update(FollowUpDeliveryAttemptRow)
            .where(
                FollowUpDeliveryAttemptRow.business_id == business_id,
                FollowUpDeliveryAttemptRow.case_id == case_id,
                FollowUpDeliveryAttemptRow.attempt_number == attempt_number,
            )
            .values(
                status=(DeliveryStatus.SENT if sent else DeliveryStatus.FAILED).value,
                twilio_sid=twilio_sid,
                updated_at=now,
            )
        )

    @staticmethod
    def _to_domain(row: FollowUpDeliveryAttemptRow) -> FollowUpDeliveryAttempt:
        return FollowUpDeliveryAttempt(
            row.business_id,
            row.case_id,
            row.attempt_number,
            DeliveryStatus(row.status),
            row.message_text,
            row.twilio_sid,
            _aware(row.created_at),
            _aware(row.updated_at),
        )


class SQLAlchemyStaffUserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, user: StaffUser) -> None:
        self.session.add(StaffUserRow(
            id=user.user_id,
            business_id=user.business_id,
            email=user.email,
            normalized_email=user.normalized_email,
            name=user.name,
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

    def get_by_email(self, normalized_email: str, *, for_update: bool = False) -> StaffUser | None:
        statement = select(StaffUserRow).where(StaffUserRow.normalized_email == normalized_email)
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._to_domain(row) if row else None

    def save(self, user: StaffUser) -> None:
        row = self.session.get(StaffUserRow, user.user_id)
        if row is None:
            raise KeyError(f"unknown staff user_id: {user.user_id}")
        row.business_id = user.business_id
        row.email = user.email
        row.name = user.name
        row.password_hash = user.password_hash
        # Add any businesses in user.business_ids not yet recorded as a
        # membership. Memberships are additive here -- nothing in the domain
        # currently removes a business from an account, so there's no
        # deletion branch to mirror.
        existing = set(
            self.session.scalars(
                select(BusinessMembershipRow.business_id).where(
                    BusinessMembershipRow.staff_user_id == user.user_id
                )
            )
        )
        for business_id in user.business_ids:
            if business_id not in existing:
                self.session.add(BusinessMembershipRow(
                    staff_user_id=user.user_id, business_id=business_id, created_at=utc_now(),
                ))

    def _to_domain(self, row: StaffUserRow) -> StaffUser:
        business_ids = tuple(
            self.session.scalars(
                select(BusinessMembershipRow.business_id)
                .where(BusinessMembershipRow.staff_user_id == row.id)
                .order_by(BusinessMembershipRow.created_at)
            )
        )
        # A pre-migration-0010 account's active business_id may not yet have
        # a backfilled membership row (e.g. a row written between the
        # migration's backfill and deploy finishing) -- always include it.
        if row.business_id is not None and row.business_id not in business_ids:
            business_ids = (*business_ids, row.business_id)
        return StaffUser(
            row.id, row.email, row.normalized_email, row.password_hash,
            row.business_id, _aware(row.created_at), business_ids, row.name,
        )


class SQLAlchemyStaffSignupAttributionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, user_id: str, attribution: SignupAttribution, *, recorded_at: datetime) -> None:
        self.session.add(StaffSignupAttributionRow(
            user_id=user_id,
            landing_path=attribution.landing_path,
            landing_from=attribution.landing_from,
            utm_source=attribution.utm_source,
            utm_medium=attribution.utm_medium,
            utm_campaign=attribution.utm_campaign,
            referrer_host=attribution.referrer_host,
            widget_opened=attribution.widget_opened,
            captured_at=attribution.captured_at,
            recorded_at=recorded_at,
        ))

    def get(self, user_id: str) -> SignupAttribution | None:
        row = self.session.get(StaffSignupAttributionRow, user_id)
        if row is None:
            return None
        return SignupAttribution(
            landing_path=row.landing_path,
            landing_from=row.landing_from,
            utm_source=row.utm_source,
            utm_medium=row.utm_medium,
            utm_campaign=row.utm_campaign,
            referrer_host=row.referrer_host,
            widget_opened=row.widget_opened,
            captured_at=_aware(row.captured_at),
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

    def get(self, session_id: str) -> StaffSession | None:
        row = self.session.get(StaffSessionRow, session_id)
        return self._to_domain(row) if row else None

    def list_for_user(self, user_id: str) -> tuple[StaffSession, ...]:
        rows = self.session.scalars(
            select(StaffSessionRow).where(StaffSessionRow.user_id == user_id).order_by(StaffSessionRow.created_at.desc())
        )
        return tuple(self._to_domain(row) for row in rows)

    def revoke(self, session_id: str, revoked_at: datetime) -> None:
        row = self.session.get(StaffSessionRow, session_id)
        if row is None:
            raise KeyError(f"unknown session_id: {session_id}")
        row.revoked_at = revoked_at

    def revoke_all_for_user(
        self, user_id: str, revoked_at: datetime, *, except_session_id: str | None = None
    ) -> int:
        statement = update(StaffSessionRow).where(
            StaffSessionRow.user_id == user_id,
            StaffSessionRow.revoked_at.is_(None),
        )
        if except_session_id is not None:
            statement = statement.where(StaffSessionRow.id != except_session_id)
        result = self.session.execute(statement.values(revoked_at=revoked_at))
        return result.rowcount or 0

    @staticmethod
    def _to_domain(row: StaffSessionRow) -> StaffSession:
        return StaffSession(
            row.id, row.user_id, row.token_hash, _aware(row.created_at), _aware(row.expires_at),
            _aware(row.revoked_at) if row.revoked_at is not None else None,
        )


class SQLAlchemyStaffSecurityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_credentials(self, user_id: str, *, for_update: bool = False) -> SecurityCredentials | None:
        statement = select(StaffSecurityCredentialRow).where(StaffSecurityCredentialRow.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._credentials(row) if row else None

    def save_credentials(self, value: SecurityCredentials) -> None:
        row = self.session.get(StaffSecurityCredentialRow, value.user_id)
        if row is None:
            self.session.add(StaffSecurityCredentialRow(
                user_id=value.user_id, totp_secret_encrypted=value.totp_secret_encrypted,
                pending_totp_secret_encrypted=value.pending_totp_secret_encrypted,
                pending_expires_at=value.pending_expires_at, two_factor_enabled_at=value.two_factor_enabled_at,
                updated_at=value.updated_at,
            ))
            return
        row.totp_secret_encrypted = value.totp_secret_encrypted
        row.pending_totp_secret_encrypted = value.pending_totp_secret_encrypted
        row.pending_expires_at = value.pending_expires_at
        row.two_factor_enabled_at = value.two_factor_enabled_at
        row.updated_at = value.updated_at

    def add_reset(self, value: PasswordResetRecord) -> None:
        self.session.add(StaffPasswordResetRow(
            id=value.reset_id, user_id=value.user_id, token_hash=value.token_hash,
            created_at=value.created_at, expires_at=value.expires_at, used_at=value.used_at,
        ))

    def get_reset_by_hash(self, token_hash: str, *, for_update: bool = False) -> PasswordResetRecord | None:
        statement = select(StaffPasswordResetRow).where(StaffPasswordResetRow.token_hash == token_hash)
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._reset(row) if row else None

    def invalidate_resets(self, user_id: str, now: datetime) -> None:
        self.session.execute(update(StaffPasswordResetRow).where(
            StaffPasswordResetRow.user_id == user_id, StaffPasswordResetRow.used_at.is_(None)
        ).values(used_at=now))

    def mark_reset_used(self, reset_id: str, now: datetime) -> None:
        self.session.execute(update(StaffPasswordResetRow).where(
            StaffPasswordResetRow.id == reset_id, StaffPasswordResetRow.used_at.is_(None)
        ).values(used_at=now))

    def add_login_challenge(self, value: LoginChallenge) -> None:
        self.session.add(StaffLoginChallengeRow(
            id=value.challenge_id, user_id=value.user_id, token_hash=value.token_hash,
            created_at=value.created_at, expires_at=value.expires_at, consumed_at=value.consumed_at,
        ))

    def get_login_challenge_by_hash(self, token_hash: str, *, for_update: bool = False) -> LoginChallenge | None:
        statement = select(StaffLoginChallengeRow).where(StaffLoginChallengeRow.token_hash == token_hash)
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._challenge(row) if row else None

    def consume_login_challenge(self, challenge_id: str, now: datetime) -> None:
        self.session.execute(update(StaffLoginChallengeRow).where(
            StaffLoginChallengeRow.id == challenge_id, StaffLoginChallengeRow.consumed_at.is_(None)
        ).values(consumed_at=now))

    def invalidate_login_challenges(self, user_id: str, now: datetime) -> None:
        self.session.execute(update(StaffLoginChallengeRow).where(
            StaffLoginChallengeRow.user_id == user_id,
            StaffLoginChallengeRow.consumed_at.is_(None),
        ).values(consumed_at=now))

    def replace_recovery_codes(self, user_id: str, values: tuple[RecoveryCode, ...]) -> None:
        self.session.execute(delete(StaffRecoveryCodeRow).where(StaffRecoveryCodeRow.user_id == user_id))
        self.session.add_all(StaffRecoveryCodeRow(
            id=value.recovery_code_id, user_id=value.user_id, code_hash=value.code_hash,
            created_at=value.created_at, used_at=value.used_at,
        ) for value in values)

    def get_recovery_code(self, user_id: str, code_hash: str, *, for_update: bool = False) -> RecoveryCode | None:
        statement = select(StaffRecoveryCodeRow).where(
            StaffRecoveryCodeRow.user_id == user_id, StaffRecoveryCodeRow.code_hash == code_hash,
            StaffRecoveryCodeRow.used_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        return self._recovery(row) if row else None

    def use_recovery_code(self, recovery_code_id: str, now: datetime) -> None:
        self.session.execute(update(StaffRecoveryCodeRow).where(
            StaffRecoveryCodeRow.id == recovery_code_id, StaffRecoveryCodeRow.used_at.is_(None)
        ).values(used_at=now))

    def list_recovery_codes(self, user_id: str) -> tuple[RecoveryCode, ...]:
        rows = self.session.scalars(select(StaffRecoveryCodeRow).where(StaffRecoveryCodeRow.user_id == user_id))
        return tuple(self._recovery(row) for row in rows)

    def add_audit_event(self, value: SecurityAuditEvent) -> None:
        self.session.add(StaffSecurityAuditEventRow(
            id=value.event_id, user_id=value.user_id, event_type=value.event_type,
            created_at=value.created_at, metadata_json=_json_value(value.metadata),
        ))

    def list_audit_events(self, user_id: str, *, limit: int = 100) -> tuple[SecurityAuditEvent, ...]:
        rows = self.session.scalars(select(StaffSecurityAuditEventRow).where(
            StaffSecurityAuditEventRow.user_id == user_id
        ).order_by(StaffSecurityAuditEventRow.created_at.desc()).limit(limit))
        return tuple(SecurityAuditEvent(row.id, row.user_id, row.event_type, _aware(row.created_at), row.metadata_json) for row in rows)

    @staticmethod
    def _credentials(row: StaffSecurityCredentialRow) -> SecurityCredentials:
        return SecurityCredentials(row.user_id, row.totp_secret_encrypted, row.pending_totp_secret_encrypted,
            _aware(row.pending_expires_at) if row.pending_expires_at else None,
            _aware(row.two_factor_enabled_at) if row.two_factor_enabled_at else None, _aware(row.updated_at))

    @staticmethod
    def _reset(row: StaffPasswordResetRow) -> PasswordResetRecord:
        return PasswordResetRecord(row.id, row.user_id, row.token_hash, _aware(row.created_at), _aware(row.expires_at), _aware(row.used_at) if row.used_at else None)

    @staticmethod
    def _challenge(row: StaffLoginChallengeRow) -> LoginChallenge:
        return LoginChallenge(row.id, row.user_id, row.token_hash, _aware(row.created_at), _aware(row.expires_at), _aware(row.consumed_at) if row.consumed_at else None)

    @staticmethod
    def _recovery(row: StaffRecoveryCodeRow) -> RecoveryCode:
        return RecoveryCode(row.id, row.user_id, row.code_hash, _aware(row.created_at), _aware(row.used_at) if row.used_at else None)


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
            sms_consent=lead.sms_consent,
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
                sms_consent=lead.sms_consent,
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
        return Lead(row.id, row.name, row.email, row.phone, row.metadata_json, sms_consent=row.sms_consent)


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
            is_test=case.is_test,
        ))

    def get(self, business_id: str, case_id: str, *, for_update: bool = False) -> ProcessCase | None:
        statement = select(ProcessCaseRow).where(
            ProcessCaseRow.business_id == business_id,
            ProcessCaseRow.id == case_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
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

    def list_for_business(
        self,
        business_id: str,
        *,
        limit: int | None = 200,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        include_test: bool = True,
    ) -> tuple[ProcessCase, ...]:
        statement = (
            select(ProcessCaseRow)
            .where(ProcessCaseRow.business_id == business_id)
            .order_by(ProcessCaseRow.updated_at.desc())
        )
        if created_at_from is not None:
            statement = statement.where(ProcessCaseRow.created_at >= created_at_from)
        if created_at_to is not None:
            statement = statement.where(ProcessCaseRow.created_at < created_at_to)
        if not include_test:
            statement = statement.where(ProcessCaseRow.is_test.is_(False))
        if limit is not None:
            statement = statement.limit(limit)
        rows = self.session.scalars(statement)
        return tuple(self._to_domain(row) for row in rows)

    def list_by_state(
        self,
        business_id: str,
        states: Sequence[ProcessState],
        *,
        limit: int = 500,
    ) -> tuple[ProcessCase, ...]:
        rows = self.session.scalars(
            select(ProcessCaseRow)
            .where(
                ProcessCaseRow.business_id == business_id,
                ProcessCaseRow.current_state.in_([state.value for state in states]),
            )
            .order_by(ProcessCaseRow.updated_at.asc())
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
            is_test=row.is_test,
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
