"""Add Stripe subscription billing fields to businesses.

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
    op.add_column("businesses", sa.Column("stripe_customer_id", sa.String(255), nullable=True))
    op.add_column("businesses", sa.Column("stripe_subscription_id", sa.String(255), nullable=True))
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
    op.add_column(
        "businesses",
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "uq_businesses_stripe_customer_id",
        "businesses",
        ["stripe_customer_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_businesses_stripe_customer_id", table_name="businesses")
    op.drop_column("businesses", "cancel_at_period_end")
    op.drop_column("businesses", "current_period_end")
    op.drop_column("businesses", "trial_ends_at")
    op.drop_column("businesses", "subscription_status")
    op.drop_column("businesses", "plan")
    op.drop_column("businesses", "stripe_subscription_id")
    op.drop_column("businesses", "stripe_customer_id")
