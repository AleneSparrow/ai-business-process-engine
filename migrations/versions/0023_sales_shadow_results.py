"""Durable, staff-only sales shadow results and evaluations.

Revision ID: 0023
Revises: 0022
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON(none_as_null=True).with_variant(postgresql.JSONB(none_as_null=True), "postgresql")


def upgrade() -> None:
    op.create_table(
        "sales_shadow_results",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("source_message_id", sa.String(255), nullable=False),
        sa.Column("approved_move", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("proposed_response_text", sa.Text(), nullable=True),
        sa.Column("delivered_response_text", sa.Text(), nullable=True),
        sa.Column("knowledge_ids", JSON_TYPE, nullable=False),
        sa.Column("business_fact_ids", JSON_TYPE, nullable=False),
        sa.Column("customer_evidence_ids", JSON_TYPE, nullable=False),
        sa.Column("violations", JSON_TYPE, nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("model_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation", sa.String(32), nullable=True),
        sa.Column("evaluated_by", sa.String(128), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"], ["process_cases.business_id", "process_cases.id"],
            ondelete="CASCADE", name="fk_sales_shadow_tenant_case",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "conversation_id"], ["conversations.business_id", "conversations.id"],
            ondelete="CASCADE", name="fk_sales_shadow_tenant_conversation",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_shadow_results"),
        sa.UniqueConstraint(
            "business_id", "case_id", "source_message_id", name="uq_sales_shadow_source_message",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','VALID','BLOCKED','PROVIDER_ERROR','VALIDATOR_ERROR','EVALUATED')",
            name="ck_sales_shadow_known_status",
        ),
        sa.CheckConstraint(
            "evaluation IS NULL OR evaluation IN ('APPROVED','UNSAFE','IRRELEVANT','WRONG_TONE')",
            name="ck_sales_shadow_known_evaluation",
        ),
        sa.CheckConstraint(
            "(status = 'EVALUATED' AND evaluation IS NOT NULL "
            "AND evaluated_by IS NOT NULL AND evaluated_at IS NOT NULL) "
            "OR (status <> 'EVALUATED' AND evaluation IS NULL "
            "AND evaluated_by IS NULL AND evaluated_at IS NULL)",
            name="ck_sales_shadow_evaluation_consistency",
        ),
    )
    op.create_index(
        "ix_sales_shadow_business_case_created", "sales_shadow_results",
        ["business_id", "case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sales_shadow_business_case_created", table_name="sales_shadow_results")
    op.drop_table("sales_shadow_results")
