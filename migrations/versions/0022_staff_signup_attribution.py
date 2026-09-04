"""First-touch attribution captured at staff signup.

Revision ID: 0022
Revises: 0021
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_signup_attribution",
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("landing_path", sa.String(200), nullable=False),
        sa.Column("landing_from", sa.String(64), nullable=True),
        sa.Column("utm_source", sa.String(128), nullable=True),
        sa.Column("utm_medium", sa.String(128), nullable=True),
        sa.Column("utm_campaign", sa.String(128), nullable=True),
        sa.Column("referrer_host", sa.String(253), nullable=True),
        sa.Column("widget_opened", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["staff_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name="pk_staff_signup_attribution"),
    )


def downgrade() -> None:
    op.drop_table("staff_signup_attribution")
