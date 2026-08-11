"""Initial tenant persistence schema.

Revision ID: 0001
Revises: None
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_VALUE = postgresql.JSONB(none_as_null=True).with_variant(sa.JSON(none_as_null=True), "sqlite")


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "business_dna",
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("configuration", JSON_VALUE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("business_id", "version"),
        sa.CheckConstraint("version > 0", name="ck_business_dna_version_positive"),
    )
    op.create_index(
        "uq_business_dna_one_active",
        "business_dna",
        ["business_id"],
        unique=True,
        postgresql_where=sa.text("active"),
        sqlite_where=sa.text("active = 1"),
    )
    op.create_table(
        "leads",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("phone", sa.String(64)),
        sa.Column("normalized_phone", sa.String(32)),
        sa.Column("email", sa.String(320)),
        sa.Column("normalized_email", sa.String(320)),
        sa.Column("metadata", JSON_VALUE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("business_id", "id", name="uq_leads_business_id_id"),
    )
    op.create_index("ix_leads_business", "leads", ["business_id"])
    op.create_index(
        "uq_leads_business_phone", "leads", ["business_id", "normalized_phone"], unique=True,
        postgresql_where=sa.text("normalized_phone IS NOT NULL"),
        sqlite_where=sa.text("normalized_phone IS NOT NULL"),
    )
    op.create_index(
        "uq_leads_business_email", "leads", ["business_id", "normalized_email"], unique=True,
        postgresql_where=sa.text("normalized_email IS NOT NULL"),
        sqlite_where=sa.text("normalized_email IS NOT NULL"),
    )
    op.create_table(
        "process_cases",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("lead_id", sa.String(128), nullable=False),
        sa.Column("current_state", sa.String(32), nullable=False),
        sa.Column("pending_human_target", sa.String(32)),
        sa.Column("metadata", JSON_VALUE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id", "lead_id"], ["leads.business_id", "leads.id"],
            name="fk_process_cases_tenant_lead", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("business_id", "id", name="uq_process_cases_business_id_id"),
        sa.CheckConstraint("version >= 0", name="ck_process_cases_version_nonnegative"),
        sa.CheckConstraint(
            "current_state IN ('NEW_LEAD','CONTACTED','QUALIFYING','QUALIFIED','BOOKED','QUOTED','FOLLOW_UP','WON','PAID','COMPLETED','REVIEW_REQUESTED','REACTIVATION','NEEDS_HUMAN','LOST','CANCELLED')",
            name="ck_process_cases_known_state",
        ),
        sa.CheckConstraint(
            "pending_human_target IS NULL OR current_state = 'NEEDS_HUMAN'",
            name="ck_process_cases_pending_human_state",
        ),
    )
    op.create_index("ix_process_cases_business_lead", "process_cases", ["business_id", "lead_id"])
    op.create_index("ix_process_cases_business_state", "process_cases", ["business_id", "current_state"])
    op.create_table(
        "process_events",
        sa.Column("id", sa.String(512), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("trigger_id", sa.String(512)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("payload", JSON_VALUE, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"], ["process_cases.business_id", "process_cases.id"],
            name="fk_process_events_tenant_case", ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_process_events_business_case_created",
        "process_events",
        ["business_id", "case_id", "created_at"],
    )
    op.create_index("ix_process_events_trigger", "process_events", ["business_id", "trigger_id"])
    op.create_table(
        "processed_messages",
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("external_message_id", sa.String(255), nullable=False),
        sa.Column("message_fingerprint", sa.String(64), nullable=False),
        sa.Column("case_id", sa.String(128)),
        sa.Column("result", JSON_VALUE),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"], ["process_cases.business_id", "process_cases.id"],
            name="fk_processed_messages_tenant_case", ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "(result IS NULL AND case_id IS NULL) OR (result IS NOT NULL AND case_id IS NOT NULL)",
            name="ck_processed_messages_completion",
        ),
        sa.PrimaryKeyConstraint("business_id", "channel", "external_message_id"),
    )
    op.create_index("ix_processed_messages_case", "processed_messages", ["business_id", "case_id"])


def downgrade() -> None:
    op.drop_table("processed_messages")
    op.drop_table("process_events")
    op.drop_table("process_cases")
    op.drop_table("leads")
    op.drop_table("business_dna")
    op.drop_table("businesses")
