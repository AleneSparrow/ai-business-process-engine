"""SQLAlchemy table mappings for PostgreSQL-compatible persistence."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


JSON_VALUE = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class Base(DeclarativeBase):
    pass


class BusinessRow(Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payment_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subscription_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="incomplete")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Not unique -- see migration 0009. The same real person/email can run
        # more than one business through this app; Lemon Squeezy assigns one
        # customer_id per email, so a second business's checkout legitimately
        # reuses the first business's customer_id. Webhook resolution never
        # relies on this being unique (it uses custom_data.business_id first
        # -- see BillingService._resolve_business_id); this index just keeps
        # the fallback lookup (get_by_payment_customer_id) fast.
        Index("ix_businesses_payment_customer_id", "payment_customer_id"),
        Index("ix_businesses_payment_subscription_id", "payment_subscription_id"),
    )


class BusinessDNARow(Base):
    __tablename__ = "business_dna"

    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("version > 0", name="ck_business_dna_version_positive"),
        Index(
            "uq_business_dna_one_active",
            "business_id",
            unique=True,
            postgresql_where=text("active"),
            sqlite_where=text("active = 1"),
        ),
    )


class CrmWebhookConnectionRow(Base):
    """One outbound webhook URL per business (e.g. a Clio/Zapier catch hook).

    Deliberately its own table, not a Business DNA field -- Business DNA is
    read into AI prompt context (BUSINESS_CONTEXT) in several places, and
    this URL is effectively a bearer secret (Zapier/Make-style hooks embed a
    token in the path). See `communication.compliance_disclaimer` for the
    contrasting case: that IS safe in Business DNA because it's meant to be
    customer-visible text, not a credential.
    """

    __tablename__ = "crm_webhook_connections"

    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    webhook_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SmsConnectionRow(Base):
    """One Twilio phone number per business. Purchased and populated by
    SmsService.provision_number_if_needed, not typed in by the business
    owner -- see that module. `phone_number` is globally unique (it's how
    an inbound Twilio webhook resolves which business a text belongs to)."""

    __tablename__ = "sms_connections"

    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    twilio_phone_sid: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StaffUserRow(Base):
    __tablename__ = "staff_users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("normalized_email", name="uq_staff_users_normalized_email"),
        Index("ix_staff_users_business", "business_id"),
    )


class BusinessMembershipRow(Base):
    """Which businesses a staff account is linked to (many-to-many). The
    legacy `staff_users.business_id` column above stays as that account's
    *active* business (must be a member here) -- see migration 0010."""

    __tablename__ = "business_memberships"

    staff_user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("staff_users.id", ondelete="CASCADE"), primary_key=True
    )
    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_business_memberships_business", "business_id"),
    )


class StaffSessionRow(Base):
    __tablename__ = "staff_sessions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_staff_sessions_token_hash"),
        Index("ix_staff_sessions_user", "user_id"),
    )


class LeadRow(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    normalized_phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    normalized_email: Mapped[str | None] = mapped_column(String(320))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_leads_business_id_id"),
        Index("ix_leads_business", "business_id"),
        Index(
            "uq_leads_business_phone",
            "business_id",
            "normalized_phone",
            unique=True,
            postgresql_where=text("normalized_phone IS NOT NULL"),
            sqlite_where=text("normalized_phone IS NOT NULL"),
        ),
        Index(
            "uq_leads_business_email",
            "business_id",
            "normalized_email",
            unique=True,
            postgresql_where=text("normalized_email IS NOT NULL"),
            sqlite_where=text("normalized_email IS NOT NULL"),
        ),
    )


class ProcessCaseRow(Base):
    __tablename__ = "process_cases"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lead_id: Mapped[str] = mapped_column(String(128), nullable=False)
    current_state: Mapped[str] = mapped_column(String(32), nullable=False)
    pending_human_target: Mapped[str | None] = mapped_column(String(32))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "lead_id"],
            ["leads.business_id", "leads.id"],
            ondelete="CASCADE",
            name="fk_process_cases_tenant_lead",
        ),
        UniqueConstraint("business_id", "id", name="uq_process_cases_business_id_id"),
        CheckConstraint("version >= 0", name="ck_process_cases_version_nonnegative"),
        CheckConstraint(
            "current_state IN ('NEW_LEAD','CONTACTED','QUALIFYING','QUALIFIED','BOOKED','QUOTED','FOLLOW_UP','WON','PAID','COMPLETED','REVIEW_REQUESTED','REACTIVATION','NEEDS_HUMAN','LOST','CANCELLED')",
            name="ck_process_cases_known_state",
        ),
        CheckConstraint(
            "pending_human_target IS NULL OR current_state = 'NEEDS_HUMAN'",
            name="ck_process_cases_pending_human_state",
        ),
        Index("ix_process_cases_business_lead", "business_id", "lead_id"),
        Index("ix_process_cases_business_state", "business_id", "current_state"),
    )


class ProcessEventRow(Base):
    __tablename__ = "process_events"

    id: Mapped[str] = mapped_column(String(512), primary_key=True)
    business_id: Mapped[str] = mapped_column(String(128), nullable=False)
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_id: Mapped[str | None] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            ondelete="CASCADE",
            name="fk_process_events_tenant_case",
        ),
        Index("ix_process_events_business_case_created", "business_id", "case_id", "created_at"),
        Index("ix_process_events_trigger", "business_id", "trigger_id"),
    )


class ProcessedMessageRow(Base):
    __tablename__ = "processed_messages"

    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    channel: Mapped[str] = mapped_column(String(64), primary_key=True)
    external_message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    message_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            ondelete="CASCADE",
            name="fk_processed_messages_tenant_case",
        ),
        CheckConstraint(
            "(result IS NULL AND case_id IS NULL) OR (result IS NOT NULL AND case_id IS NOT NULL)",
            name="ck_processed_messages_completion",
        ),
        Index("ix_processed_messages_case", "business_id", "case_id"),
    )


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(String(128))
    case_id: Mapped[str | None] = mapped_column(String(128))
    external_session_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False, default=dict
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "lead_id"],
            ["leads.business_id", "leads.id"],
            name="fk_conversations_tenant_lead",
        ),
        ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            name="fk_conversations_tenant_case",
        ),
        UniqueConstraint("business_id", "id", name="uq_conversations_business_id_id"),
        UniqueConstraint("business_id", "token_hash", name="uq_conversations_business_token"),
        UniqueConstraint(
            "business_id",
            "channel",
            "external_session_id",
            name="uq_conversations_business_external_session",
        ),
        CheckConstraint("version >= 0", name="ck_conversations_version_nonnegative"),
        CheckConstraint(
            "status IN ('ai_active','human_takeover_requested','human_takeover_active','closed')",
            name="ck_conversations_known_status",
        ),
        CheckConstraint(
            "(lead_id IS NULL AND case_id IS NULL) OR (lead_id IS NOT NULL AND case_id IS NOT NULL)",
            name="ck_conversations_case_link_complete",
        ),
        CheckConstraint(
            "token_expires_at > created_at",
            name="ck_conversations_token_expiry",
        ),
        CheckConstraint(
            "updated_at >= created_at AND last_activity_at >= created_at",
            name="ck_conversations_timestamp_order",
        ),
        CheckConstraint(
            "token_revoked_at IS NULL OR token_revoked_at >= created_at",
            name="ck_conversations_revocation_order",
        ),
        Index("ix_conversations_business_activity", "business_id", "last_activity_at"),
        Index("ix_conversations_business_status", "business_id", "status"),
    )


class ConversationMessageRow(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    content_fingerprint: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False, default=dict
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "conversation_id"],
            ["conversations.business_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_conversation_messages_tenant_conversation",
        ),
        UniqueConstraint(
            "business_id",
            "conversation_id",
            "sequence_number",
            name="uq_conversation_messages_sequence",
        ),
        UniqueConstraint(
            "business_id",
            "conversation_id",
            "external_message_id",
            name="uq_conversation_messages_external_id",
        ),
        CheckConstraint("sequence_number > 0", name="ck_conversation_messages_sequence_positive"),
        CheckConstraint(
            "direction IN ('inbound','outbound')",
            name="ck_conversation_messages_direction",
        ),
        CheckConstraint(
            "role IN ('customer','assistant','human','system')",
            name="ck_conversation_messages_role",
        ),
        CheckConstraint(
            "(direction = 'inbound' AND role = 'customer') OR "
            "(direction = 'outbound' AND role IN ('assistant','human','system'))",
            name="ck_conversation_messages_direction_role",
        ),
        CheckConstraint(
            "(external_message_id IS NULL AND content_fingerprint IS NULL) OR "
            "(external_message_id IS NOT NULL AND content_fingerprint IS NOT NULL)",
            name="ck_conversation_messages_idempotency_pair",
        ),
        Index(
            "ix_conversation_messages_business_order",
            "business_id",
            "conversation_id",
            "sequence_number",
        ),
    )


class BookingRow(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lead_id: Mapped[str] = mapped_column(String(128), nullable=False)
    service_id: Mapped[str] = mapped_column(String(128), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False, default=dict
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            name="fk_bookings_tenant_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["business_id", "lead_id"],
            ["leads.business_id", "leads.id"],
            name="fk_bookings_tenant_lead",
        ),
        UniqueConstraint("business_id", "id", name="uq_bookings_business_id_id"),
        UniqueConstraint("business_id", "case_id", name="uq_bookings_business_case"),
        CheckConstraint("end_at > start_at", name="ck_bookings_time_order"),
        CheckConstraint("updated_at >= created_at", name="ck_bookings_timestamp_order"),
        CheckConstraint("version >= 0", name="ck_bookings_version_nonnegative"),
        CheckConstraint(
            "status IN ('PENDING','CONFIRMED','CANCELLED','RESCHEDULED','COMPLETED')",
            name="ck_bookings_known_status",
        ),
        Index(
            "ix_bookings_business_service_slot",
            "business_id",
            "service_id",
            "start_at",
            "end_at",
            "status",
        ),
        Index("ix_bookings_business_lead", "business_id", "lead_id"),
    )


class QuoteRow(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lead_id: Mapped[str] = mapped_column(String(128), nullable=False)
    service_id: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pricing_basis: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False, default=dict
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            name="fk_quotes_tenant_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["business_id", "lead_id"],
            ["leads.business_id", "leads.id"],
            name="fk_quotes_tenant_lead",
        ),
        UniqueConstraint("business_id", "id", name="uq_quotes_business_id_id"),
        UniqueConstraint("business_id", "case_id", name="uq_quotes_business_case"),
        CheckConstraint("subtotal >= 0 AND total >= subtotal", name="ck_quotes_amounts"),
        CheckConstraint("valid_until > created_at", name="ck_quotes_validity"),
        CheckConstraint("updated_at >= created_at", name="ck_quotes_timestamp_order"),
        CheckConstraint("version >= 0", name="ck_quotes_version_nonnegative"),
        CheckConstraint(
            "status IN ('DRAFT','PRESENTED','ACCEPTED','REJECTED','EXPIRED','CANCELLED')",
            name="ck_quotes_known_status",
        ),
        Index("ix_quotes_business_status_validity", "business_id", "status", "valid_until"),
        Index("ix_quotes_business_lead", "business_id", "lead_id"),
    )


class QuoteLineRow(Base):
    __tablename__ = "quote_lines"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_id: Mapped[str] = mapped_column(String(128), nullable=False)
    quote_id: Mapped[str] = mapped_column(String(128), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "quote_id"],
            ["quotes.business_id", "quotes.id"],
            name="fk_quote_lines_tenant_quote",
            ondelete="CASCADE",
        ),
        UniqueConstraint("business_id", "quote_id", "position", name="uq_quote_lines_position"),
        CheckConstraint("position > 0", name="ck_quote_lines_position_positive"),
        CheckConstraint(
            "quantity > 0 AND unit_amount >= 0 AND line_total >= 0",
            name="ck_quote_lines_amounts",
        ),
        Index("ix_quote_lines_business_quote", "business_id", "quote_id"),
    )


class PaymentRequestRow(Base):
    __tablename__ = "payment_requests"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    quote_id: Mapped[str | None] = mapped_column(String(128))
    booking_id: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False, default=dict
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            name="fk_payment_requests_tenant_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["business_id", "quote_id"],
            ["quotes.business_id", "quotes.id"],
            name="fk_payment_requests_tenant_quote",
        ),
        ForeignKeyConstraint(
            ["business_id", "booking_id"],
            ["bookings.business_id", "bookings.id"],
            name="fk_payment_requests_tenant_booking",
        ),
        UniqueConstraint("business_id", "id", name="uq_payment_requests_business_id_id"),
        UniqueConstraint(
            "business_id",
            "case_id",
            "payment_type",
            name="uq_payment_requests_business_case_type",
        ),
        CheckConstraint("amount >= 0", name="ck_payment_requests_amount"),
        CheckConstraint("updated_at >= created_at", name="ck_payment_requests_timestamp_order"),
        CheckConstraint("expires_at > created_at", name="ck_payment_requests_expiry"),
        CheckConstraint("version >= 0", name="ck_payment_requests_version_nonnegative"),
        CheckConstraint("payment_type IN ('DEPOSIT','FINAL')", name="ck_payment_requests_type"),
        CheckConstraint(
            "status IN ('PENDING','READY','PAID','FAILED','CANCELLED','EXPIRED')",
            name="ck_payment_requests_known_status",
        ),
        Index("ix_payment_requests_business_status", "business_id", "status", "expires_at"),
        Index("ix_payment_requests_business_case", "business_id", "case_id"),
    )
