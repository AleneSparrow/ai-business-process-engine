"""Durable outbox for asynchronous sales shadow generation.

Revision ID: 0024
Revises: 0023
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_conversation_messages_tenant_id", "conversation_messages",
        ["business_id", "conversation_id", "id"],
    )
    op.create_table(
        "sales_shadow_jobs",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("source_message_id", sa.String(128), nullable=False),
        sa.Column("response_message_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_category", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"], ondelete="CASCADE",
            name="fk_sales_shadow_jobs_tenant_case"),
        sa.ForeignKeyConstraint(["business_id", "conversation_id"],
            ["conversations.business_id", "conversations.id"], ondelete="CASCADE",
            name="fk_sales_shadow_jobs_tenant_conversation"),
        sa.ForeignKeyConstraint(["business_id", "conversation_id", "source_message_id"],
            ["conversation_messages.business_id", "conversation_messages.conversation_id", "conversation_messages.id"],
            ondelete="CASCADE", name="fk_sales_shadow_jobs_tenant_source_message"),
        sa.ForeignKeyConstraint(["business_id", "conversation_id", "response_message_id"],
            ["conversation_messages.business_id", "conversation_messages.conversation_id", "conversation_messages.id"],
            ondelete="CASCADE", name="fk_sales_shadow_jobs_tenant_response_message"),
        sa.PrimaryKeyConstraint("id", name="pk_sales_shadow_jobs"),
        sa.UniqueConstraint("business_id", "case_id", "source_message_id",
            name="uq_sales_shadow_jobs_source_message"),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED')",
            name="ck_sales_shadow_jobs_known_status"),
        sa.CheckConstraint("retry_count >= 0 AND max_retries > 0 AND retry_count <= max_retries",
            name="ck_sales_shadow_jobs_retry_counts"),
        sa.CheckConstraint("(lease_owner IS NULL) = (lease_expires_at IS NULL)",
            name="ck_sales_shadow_jobs_lease_complete"),
    )
    op.create_index("ix_sales_shadow_jobs_due", "sales_shadow_jobs", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_sales_shadow_jobs_due", table_name="sales_shadow_jobs")
    op.drop_table("sales_shadow_jobs")
    op.drop_constraint("uq_conversation_messages_tenant_id", "conversation_messages", type_="unique")
