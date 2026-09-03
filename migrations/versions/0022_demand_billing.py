"""Demand add-on subscription fields on businesses.

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
    op.add_column(
        "businesses",
        sa.Column("demand_payment_subscription_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "demand_subscription_status",
            sa.String(32),
            nullable=False,
            server_default="incomplete",
        ),
    )
    op.add_column(
        "businesses",
        sa.Column("demand_trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column("demand_current_period_end", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column("demand_billing_event_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_businesses_demand_payment_subscription_id",
        "businesses",
        ["demand_payment_subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_businesses_demand_payment_subscription_id", table_name="businesses")
    op.drop_column("businesses", "demand_billing_event_at")
    op.drop_column("businesses", "demand_current_period_end")
    op.drop_column("businesses", "demand_trial_ends_at")
    op.drop_column("businesses", "demand_subscription_status")
    op.drop_column("businesses", "demand_payment_subscription_id")
