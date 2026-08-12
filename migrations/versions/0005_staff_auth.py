"""Add staff users and sessions for authenticated business-owner access.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_users",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("normalized_email", name="uq_staff_users_normalized_email"),
    )
    op.create_index("ix_staff_users_business", "staff_users", ["business_id"])

    op.create_table(
        "staff_sessions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["staff_users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_staff_sessions_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_staff_sessions_expiry_after_creation"),
    )
    op.create_index("ix_staff_sessions_user", "staff_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_staff_sessions_user", table_name="staff_sessions")
    op.drop_table("staff_sessions")
    op.drop_index("ix_staff_users_business", table_name="staff_users")
    op.drop_table("staff_users")
