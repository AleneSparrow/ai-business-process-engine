"""Add reset, two-factor, recovery, and staff security-audit persistence.

Revision ID: 0018
Revises: 0017
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_security_credentials",
        sa.Column("user_id", sa.String(128), sa.ForeignKey("staff_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("totp_secret_encrypted", sa.Text()),
        sa.Column("pending_totp_secret_encrypted", sa.Text()),
        sa.Column("pending_expires_at", sa.DateTime(timezone=True)),
        sa.Column("two_factor_enabled_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "staff_password_resets",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("token_hash", name="uq_staff_password_resets_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_staff_password_resets_expiry"),
    )
    op.create_index("ix_staff_password_resets_user_expiry", "staff_password_resets", ["user_id", "expires_at"])
    op.create_table(
        "staff_login_challenges",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("token_hash", name="uq_staff_login_challenges_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_staff_login_challenges_expiry"),
    )
    op.create_index("ix_staff_login_challenges_user_expiry", "staff_login_challenges", ["user_id", "expires_at"])
    op.create_table(
        "staff_recovery_codes",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_staff_recovery_codes_user_hash"),
    )
    op.create_index("ix_staff_recovery_codes_user_active", "staff_recovery_codes", ["user_id", "used_at"])
    op.create_table(
        "staff_security_audit_events",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(none_as_null=True), nullable=False),
    )
    op.create_index("ix_staff_security_audit_events_user_created", "staff_security_audit_events", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_staff_security_audit_events_user_created", table_name="staff_security_audit_events")
    op.drop_table("staff_security_audit_events")
    op.drop_index("ix_staff_recovery_codes_user_active", table_name="staff_recovery_codes")
    op.drop_table("staff_recovery_codes")
    op.drop_index("ix_staff_login_challenges_user_expiry", table_name="staff_login_challenges")
    op.drop_table("staff_login_challenges")
    op.drop_index("ix_staff_password_resets_user_expiry", table_name="staff_password_resets")
    op.drop_table("staff_password_resets")
    op.drop_table("staff_security_credentials")
