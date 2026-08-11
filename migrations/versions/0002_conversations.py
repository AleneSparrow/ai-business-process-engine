"""Add tenant-scoped conversations and ordered messages.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_VALUE = postgresql.JSONB(none_as_null=True).with_variant(sa.JSON(none_as_null=True), "sqlite")


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("lead_id", sa.String(128)),
        sa.Column("case_id", sa.String(128)),
        sa.Column("external_session_id", sa.String(255)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_revoked_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", JSON_VALUE, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_id", "lead_id"],
            ["leads.business_id", "leads.id"],
            name="fk_conversations_tenant_lead",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            name="fk_conversations_tenant_case",
        ),
        sa.UniqueConstraint("business_id", "id", name="uq_conversations_business_id_id"),
        sa.UniqueConstraint("business_id", "token_hash", name="uq_conversations_business_token"),
        sa.UniqueConstraint(
            "business_id", "channel", "external_session_id",
            name="uq_conversations_business_external_session",
        ),
        sa.CheckConstraint("version >= 0", name="ck_conversations_version_nonnegative"),
        sa.CheckConstraint(
            "status IN ('ai_active','human_takeover_requested','human_takeover_active','closed')",
            name="ck_conversations_known_status",
        ),
        sa.CheckConstraint(
            "(lead_id IS NULL AND case_id IS NULL) OR (lead_id IS NOT NULL AND case_id IS NOT NULL)",
            name="ck_conversations_case_link_complete",
        ),
        sa.CheckConstraint("token_expires_at > created_at", name="ck_conversations_token_expiry"),
    )
    op.create_index(
        "ix_conversations_business_activity", "conversations", ["business_id", "last_activity_at"]
    )
    op.create_index(
        "ix_conversations_business_status", "conversations", ["business_id", "status"]
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_message_id", sa.String(255)),
        sa.Column("content_fingerprint", sa.String(64)),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("metadata", JSON_VALUE, nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id", "conversation_id"],
            ["conversations.business_id", "conversations.id"],
            name="fk_conversation_messages_tenant_conversation",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "business_id", "conversation_id", "sequence_number",
            name="uq_conversation_messages_sequence",
        ),
        sa.UniqueConstraint(
            "business_id", "conversation_id", "external_message_id",
            name="uq_conversation_messages_external_id",
        ),
        sa.CheckConstraint("sequence_number > 0", name="ck_conversation_messages_sequence_positive"),
        sa.CheckConstraint("direction IN ('inbound','outbound')", name="ck_conversation_messages_direction"),
        sa.CheckConstraint(
            "role IN ('customer','assistant','human','system')",
            name="ck_conversation_messages_role",
        ),
        sa.CheckConstraint(
            "(direction = 'inbound' AND role = 'customer') OR "
            "(direction = 'outbound' AND role IN ('assistant','human','system'))",
            name="ck_conversation_messages_direction_role",
        ),
    )
    op.create_index(
        "ix_conversation_messages_business_order",
        "conversation_messages",
        ["business_id", "conversation_id", "sequence_number"],
    )


def downgrade() -> None:
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
