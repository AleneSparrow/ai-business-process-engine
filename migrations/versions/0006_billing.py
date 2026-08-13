"""Add Lemon Squeezy subscription billing fields to businesses.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("payment_customer_id", sa.String(255), nullable=True))
    op.add_column("businesses", sa.Column("payment_subscription_id", sa.String(255), nullable=True))
    op.add_column("businesses", sa.Column("plan", sa.String(32), nullable=True))
    op.add_column(
        "businesses",
        sa.Column(
            "subscription_status",
            sa.String(32),
            nullable=False,
            server_default="incomplete",
        ),
    )
    op.add_column("businesses", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("businesses", sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "uq_businesses_payment_customer_id",
        "businesses",
        ["payment_customer_id"],
        unique=True,
    )
    op.create_index(
        "ix_businesses_payment_subscription_id",
        "businesses",
        ["payment_subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_businesses_payment_subscription_id", table_name="businesses")
    op.drop_index("uq_businesses_payment_customer_id", table_name="businesses")
    op.drop_column("businesses", "current_period_end")
    op.drop_column("businesses", "trial_ends_at")
    op.drop_column("businesses", "subscription_status")
    op.drop_column("businesses", "plan")
    op.drop_column("businesses", "payment_subscription_id")
    op.drop_column("businesses", "payment_customer_id")
