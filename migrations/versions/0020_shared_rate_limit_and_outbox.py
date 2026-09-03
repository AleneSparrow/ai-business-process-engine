"""Shared rate-limit hits and integration outbox.

Revision ID: 0020
Revises: 0019
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "rate_limit_hits",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("rate_key", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rate_limit_hits_key_time", "rate_limit_hits", ["rate_key", "occurred_at"])
    op.create_table(
        "integration_outbox",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "business_id",
            sa.String(128),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", JSON_TYPE, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED')", name="ck_integration_outbox_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_integration_outbox_attempts"),
    )
    op.create_index("ix_integration_outbox_due", "integration_outbox", ["status", "next_attempt_at"])
    op.create_index("ix_integration_outbox_business", "integration_outbox", ["business_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_integration_outbox_business", table_name="integration_outbox")
    op.drop_index("ix_integration_outbox_due", table_name="integration_outbox")
    op.drop_table("integration_outbox")
    op.drop_index("ix_rate_limit_hits_key_time", table_name="rate_limit_hits")
    op.drop_table("rate_limit_hits")
