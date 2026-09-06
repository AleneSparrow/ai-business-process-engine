"""Governed sales conversation profiles, turns, playbooks, and knowledge.

Revision ID: 0022
Revises: 0021
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON(none_as_null=True).with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)


def upgrade() -> None:
    op.create_table(
        "sales_profiles",
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("customer_goal", sa.Text(), nullable=True),
        sa.Column("current_problem", sa.Text(), nullable=True),
        sa.Column("desired_outcome", sa.Text(), nullable=True),
        sa.Column("decision_criteria", JSON_TYPE, nullable=False),
        sa.Column("active_objection", JSON_TYPE, nullable=True),
        sa.Column("commitment_level", sa.String(32), nullable=False),
        sa.Column("preferred_channel", sa.String(64), nullable=True),
        sa.Column("preferred_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_move", sa.String(64), nullable=True),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            ondelete="CASCADE",
            name="fk_sales_profiles_tenant_case",
        ),
        sa.PrimaryKeyConstraint("business_id", "case_id", name="pk_sales_profiles"),
        sa.CheckConstraint("version >= 0", name="ck_sales_profiles_version_nonnegative"),
        sa.CheckConstraint(
            "stage IN ('GREETING','DISCOVERY','NEEDS_CONFIRMED','PRESENTATION','OBJECTION_HANDLING','COMMITMENT','BOOKING','NURTURE','FOLLOW_UP','WON','LOST','HUMAN_REVIEW')",
            name="ck_sales_profiles_known_stage",
        ),
        sa.CheckConstraint(
            "commitment_level IN ('UNKNOWN','CURIOUS','INTERESTED','CONSIDERING','READY_FOR_NEXT_STEP','DECLINED')",
            name="ck_sales_profiles_known_commitment",
        ),
    )
    op.create_index("ix_sales_profiles_business_stage", "sales_profiles", ["business_id", "stage"])

    op.create_table(
        "sales_playbook_versions",
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("configuration", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("business_id", "version", name="pk_sales_playbook_versions"),
        sa.CheckConstraint("version > 0", name="ck_sales_playbook_versions_positive"),
        sa.CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','ARCHIVED')",
            name="ck_sales_playbook_versions_known_status",
        ),
        sa.CheckConstraint(
            "(status = 'PUBLISHED' AND published_at IS NOT NULL) OR status <> 'PUBLISHED'",
            name="ck_sales_playbook_versions_published_at",
        ),
    )
    op.create_index(
        "uq_sales_playbook_one_published",
        "sales_playbook_versions",
        ["business_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
        sqlite_where=sa.text("status = 'PUBLISHED'"),
    )

    op.create_table(
        "sales_knowledge_cards",
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("knowledge_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", JSON_TYPE, nullable=False),
        sa.Column("principle", sa.Text(), nullable=False),
        sa.Column("applicable_when", JSON_TYPE, nullable=False),
        sa.Column("prohibited_when", JSON_TYPE, nullable=False),
        sa.Column("required_sequence", JSON_TYPE, nullable=False),
        sa.Column("forbidden_actions", JSON_TYPE, nullable=False),
        sa.Column("approved_examples", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["staff_users.id"],
            name="fk_sales_knowledge_cards_reviewer",
        ),
        sa.PrimaryKeyConstraint(
            "business_id", "knowledge_id", "version",
            name="pk_sales_knowledge_cards",
        ),
        sa.CheckConstraint("version > 0", name="ck_sales_knowledge_cards_version_positive"),
        sa.CheckConstraint(
            "status IN ('CANDIDATE','APPROVED','REJECTED')",
            name="ck_sales_knowledge_cards_known_status",
        ),
        sa.CheckConstraint(
            "(reviewed_at IS NULL AND reviewed_by IS NULL) OR "
            "(reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="ck_sales_knowledge_cards_review_audit_complete",
        ),
    )
    op.create_index(
        "ix_sales_knowledge_cards_business_status",
        "sales_knowledge_cards",
        ["business_id", "status"],
    )

    op.create_table(
        "sales_objections",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("objection_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.Column("source_message_id", sa.String(255), nullable=False),
        sa.Column("evidence_excerpt", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["sales_profiles.business_id", "sales_profiles.case_id"],
            ondelete="CASCADE",
            name="fk_sales_objections_tenant_profile",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_objections"),
        sa.CheckConstraint(
            "objection_type IN ('PRICE','TRUST','TIMING','FIT','AUTHORITY','COMPETITOR','NEED_TO_THINK','OTHER')",
            name="ck_sales_objections_known_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DIAGNOSED','ADDRESSED','RESOLVED','DEFERRED','HUMAN_REVIEW')",
            name="ck_sales_objections_known_status",
        ),
        sa.CheckConstraint(
            "version >= 0", name="ck_sales_objections_version_non_negative"
        ),
    )
    op.create_index(
        "ix_sales_objections_business_case",
        "sales_objections",
        ["business_id", "case_id", "created_at"],
    )

    op.create_table(
        "sales_turns",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=True),
        sa.Column("source_message_id", sa.String(255), nullable=False),
        sa.Column("playbook_version", sa.Integer(), nullable=True),
        sa.Column("stage_before", sa.String(32), nullable=False),
        sa.Column("stage_after", sa.String(32), nullable=False),
        sa.Column("move", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column("knowledge_ids", JSON_TYPE, nullable=False),
        sa.Column("business_fact_ids", JSON_TYPE, nullable=False),
        sa.Column("customer_evidence", JSON_TYPE, nullable=False),
        sa.Column("analysis", JSON_TYPE, nullable=False),
        sa.Column("validation", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            ondelete="CASCADE",
            name="fk_sales_turns_tenant_case",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "conversation_id"],
            ["conversations.business_id", "conversations.id"],
            name="fk_sales_turns_tenant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "playbook_version"],
            ["sales_playbook_versions.business_id", "sales_playbook_versions.version"],
            name="fk_sales_turns_tenant_playbook",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_turns"),
        sa.UniqueConstraint(
            "business_id", "case_id", "source_message_id",
            name="uq_sales_turns_source_message",
        ),
    )
    op.create_index(
        "ix_sales_turns_business_case_created",
        "sales_turns",
        ["business_id", "case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sales_turns_business_case_created", table_name="sales_turns")
    op.drop_table("sales_turns")
    op.drop_index("ix_sales_objections_business_case", table_name="sales_objections")
    op.drop_table("sales_objections")
    op.drop_index("ix_sales_knowledge_cards_business_status", table_name="sales_knowledge_cards")
    op.drop_table("sales_knowledge_cards")
    op.drop_index("uq_sales_playbook_one_published", table_name="sales_playbook_versions")
    op.drop_table("sales_playbook_versions")
    op.drop_index("ix_sales_profiles_business_stage", table_name="sales_profiles")
    op.drop_table("sales_profiles")
